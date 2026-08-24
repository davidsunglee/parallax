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
of different widths and two merged rows at once, over a source view row whose
width belongs to the source level rather than to either concrete — and a
duplicate of either merges onto the logical node its broad projection made.

**Each level of the plan owns a source of its own.** A schema fixes one slot
tuple per source level and resolved concrete, where the source level is the plan
level that produced the projection, so the workload reads its roots at level 0,
every child of the broad hop at level 1, and the duplicates of a second hop below
that one at level 2 — with the second hop's own slot on the source its parents
came from, written to every one of them. That is what keeps the slot arithmetic a
count of positions production lays out rather than of positions the workload
declared for itself. What those slots HOLD is exactly what each one's own
relationship join returns, in every state below as well, and no two of the root's
views join alike: a child's ``parentId`` names the root the broad hop gathered it
under, its ``armId`` names that same root only where the narrowed arm gathers it,
and its ``twinId`` names another child and no root at all, which is what leaves
the declared-and-empty views empty. So the fan-out being priced is the one a query
returns rather than a subset the composition chose — asserted in both directions,
against the accepted model's own joins, over every row the graph holds. What that
leaves outside is provenance rather than shape: the arm names the projections the
broad hop already read instead of converting its own, so what is checked is which
LOGICAL NODES a view holds, not which source level each was read at.

**Every measured projection also carries Value Object occurrences**, a top-level
One holding a nested One and a nested Many whose every element holds one more,
beside a top-level Many, because the representation this replaced spent more of
its per-cell cost inside documents than on Attributes: a record, an occurrence,
and a per-leaf carrier each. Their shape is pinned across the grid — four more
crossed axes would buy nothing the first three do not already refuse — and read
instead as four steps of their own, one per population an axis can move: the
leaves inside a record, the elements a Many holds, and the top-level occurrences
a projection declares of each multiplicity, which are two steps because the
production reduction is two branches.

**What no axis moves is read as a total instead.** How many occurrences a
document NESTS is a property of the declaration, so it stands still under every
axis above and a cost charged once per nested occurrence is a constant per
projection that every step absorbs. The whole document is therefore also read
against a graph of the same shape that declares no Value Object at all, priced by
a recursion over the declaration rather than by a term per level: every
occurrence, every record, and every position, at whatever depth a declaration
reaches. That is what closes the DECLARATION at every depth at once rather than
one level deep — widening the axis a level at a time would leave the level below
it exactly where the nested one was.

**What a declaration cannot close is the state its positions hold.** Every
reading above converts rows whose every declared member is supplied, so a cost
charged on a zero-value branch is on neither side of any difference between two
of them: a Many loaded empty reduces to the interpreter's own shared `()`, a One
stored null or omitted to `None`, and a member a read never carried to `ABSENT`.
The same exact total is therefore read once more over the widest declaration in
each state a conforming read can leave its positions in, with the price
state-aware — a zeroed occurrence costs its position and nothing under it. Those
states are a closed set rather than the ones anyone thought of, and closed by
assertion: the union of the states they put each kind of position in is exactly
what `python.md` admits for that kind, one nesting rank, the leaves, and the
Attributes no join reads at a time, in both spellings a stored document has, plus
the read that carried no document column at all. The primary key and the two join
Attributes stay carried through every one of them, because a row holding one of
those zero is not this graph in another state but a different graph — one whose
fan-out no query would have returned.

**What the readings say, in the order they get stronger.** The whole grid sits on
one affine function of the three parameters fitted from its four smallest points,
which refuses any cross term — a slot cost sized per member, say. Then each step
is graded against exactly what the compact representation can charge: one pointer
per member per row, one per arm where the edge is recorded and one where it
resolves, one per slot in every row a slot widens, one per Value Object leaf in
every record that carries it, one whole positional row and its naming position
per record, one position and one record per One occurrence, and one position, one
row of elements, and one record per element per Many occurrence. Then the whole
declared document, exactly, at every point that declares one — and that same
total again in every presence state the widest declaration's positions admit.
Those readings are the ones that name "no per-cell carrier" in arithmetic, and
each is read beside the control that proves it detects one —
:func:`test_the_member_step_is_what_refuses_a_representation_that_wraps_every_cell`
wraps every member cell, stays exactly affine, and fails only at the member step;
:func:`test_the_leaf_step_is_what_refuses_a_representation_wrapping_every_document_cell`
wraps every Value Object cell and fails only at the leaf step;
:func:`test_the_record_step_is_what_refuses_a_representation_wrapping_every_record`,
:func:`test_the_one_occurrence_step_is_what_refuses_a_wrapper_around_a_one_occurrence`,
and
:func:`test_the_many_occurrence_step_is_what_refuses_a_wrapper_around_a_many_occurrence`
wrap what a step holding its own population fixed cannot see at all, the last two
one multiplicity branch at a time; and
:func:`test_the_whole_document_reading_is_what_refuses_a_wrapper_around_a_nested_occurrence`
wraps what no step here holds a count of, leaving all four of them exactly at
their priced values and only the total off; and
:func:`test_the_state_readings_are_what_refuse_a_wrapper_around_a_position_stored_zero`
wraps what a carried document has none of, leaving the total exact at every point
that declares one and failing at every state but the carried one.

Exported names carry no leading underscore only where another module imports
them; nothing imports this one.
"""

from __future__ import annotations

import struct
import sys
import tracemalloc
from collections.abc import Callable, Iterator, Mapping, Sequence
from functools import cache
from typing import Final, NamedTuple, cast

import pytest
from memory_instruments import Seam, retained, survivors, warmed

from parallax.core.base import Float64, Int64
from parallax.core.entity._layout import CatalogedModel, EntityLayout, LayoutCatalog
from parallax.core.entity._model import model_of
from parallax.core.metamodel import (
    AttributeIdentity,
    AttributeMetadata,
    EntityIdentity,
    Metamodel,
    Multiplicity,
    NestedValueObjectMetadata,
    PrimaryKey,
    RelationshipIdentity,
    ValueObjectMetadata,
    entity_by_name,
)
from parallax.core.relationship import view as relationship_view
from parallax.core.temporal_read import Pin
from parallax.descriptor import domain_model_from_document
from parallax.snapshot.materialize import SnapshotGraph, merge_graph_input
from parallax.snapshot.materialize._convert import LevelContext, convert_row
from parallax.snapshot.materialize._graph import ABSENT, GraphBuilder, GraphRows, graph_rows
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
_BROAD_SOURCE: Final = 1
_TWIN_SOURCE: Final = 2
"""The three source levels the workload's plan produces projections at.

``handle/_read`` converts plan level ``i`` at source ``i + 1``, so no two levels
ever share a source: the roots are level 0, the broad hop below them reads every
child at source 1, and the ``twin`` hop below THAT — a many-to-one each child
names, whose rows are children the broad hop already read — reads its duplicates
at source 2."""

_CHILDREN: Final = 6
_DUPLICATES: Final = 2
"""Children per parent, and how many distinct children their ``twin`` references
name, which is how many of them the twin hop converts a second time. Duplicates
are what make projections and logical nodes different counts, so a reading
charged per logical node cannot pass for one charged per projection."""

_CELLS: Final = 4
_LARGER: Final = 8
"""Independent parent-and-children cells, at two sizes. The grid is measured at
the first; the second is measured at four points alone, which is all the second
fit needs to say whether each step grew with the rows it charges."""

_MEMBERS: Final = (4, 5, 8, 16)
"""Applicable Attributes on the measured Entity. The two smallest are one apart,
so their difference is what one more member costs rather than a ratio, and the
largest is four times the smallest — far enough that a cost quadratic in the row
width would be whole members off the line rather than within one member of it.

The smallest count is the primary key and the three join Attributes alone, which
:data:`_JOIN_KEYS` carries in every state, so the Attributes a state zeroes at
that count are the two concretes' own."""

_SLOTS: Final = (2, 3, 4)
"""Relationship views the plan's root-parented levels declare. Two are always
written — the broad view holding every child, and the narrowed arm the third axis
varies — and the rest are levels that gathered a parent and found nothing, which
is what a declared-and-empty slot is. Four is the ceiling deliberately: a layout
indexes its slots by a dictionary, a merged layout's union runs one wider than
this because of the child-side ``twin`` slot, and a sixth entry in that union
would resize one and put a capacity step into a reading that is otherwise
exact."""

_ARMS: Final = (1, 2, 4)
"""Children the narrowed arm gathers, and therefore projection references it
records.

What varies down this axis is the RESULT SET of one relationship query rather
than a slice this module chose: the arm joins the root's key against an arm key
only the first ``arms`` children of a cell carry, so the rest are rows that hop
cannot return. That is why the count is a row-set fact and lives in
:attr:`_Point.shape` beside the member and document counts.

Those references are aliased onto the projections the broad hop already read
rather than converted a second time, which is the one simplification this
workload makes and the reason the axis reads edges alone: the children the arm
does not name are still reached through the broad view, so no count the merge
sizes a table by moves with it. Converting the arm instead would put a whole
member row — and therefore a term in the PRODUCT of this axis and the member
axis — into a reading meant to price two positions."""

_LEAVES: Final = (1, 2)
"""Leaves on the nested records the ``mark`` occurrence holds — its ``inner``, and
each element of its ``inners``. Two counts one apart, read as a step rather than
crossed into the grid: the occurrence shape is the same at every grid point, so
what this axis answers is what one more Value Object leaf costs and nothing about
the other three."""

_ELEMENTS: Final = (2, 3)
"""Elements in each Many occurrence. More than one at the smaller count, so a cost
charged per Value Object RECORD is a different number from one charged per
projection row; read as a step of its own for what one more element costs, which
is the one axis that moves the record and element populations while holding the
leaves inside them fixed. An element of the nested Many brings the ``stamp`` its
own declaration nests under it, so this is also the axis that prices a record
reached only by descending a Many.

Zero is not a point of this axis but a STATE of the occurrence — the read
contract's own zero value, reached by storing nothing where these rows store
elements — and is read as :data:`_STATES`. Nothing between the two counts here is
a state: the Many branch has no predicate on how many elements a nonempty
occurrence holds, so what one more of them costs is all this axis has to say."""

_ONES: Final = (1, 2)
"""Top-level ONE Value Objects the measured Entity declares: ``mark`` at the
smaller count and ``spare`` beside it at the larger. One of the two axes that move
the occurrence population alone — one more occurrence per projection, at the same
member, leaf, and element counts. Zero is not a point of this axis but a whole
model of its own, :data:`_BARE`."""

_MANYS: Final = (1, 2)
"""Top-level MANY Value Objects the measured Entity declares: ``marks`` at the
smaller count and ``notes`` beside it at the larger.

The other occurrence axis, and separate from :data:`_ONES` because the
production reduction is separate: a Many occurrence is structured through its own
branch, reducing to a row per element, where a One reduces to a single row or to
nothing. A cost charged only on the Many branch is fixed per projection, so it
stands still under every other axis here — the member, slot, and arm crossing,
the leaf and element steps inside a document, and the One-occurrence step
alike."""

_LABELS: Final = 1
"""Leaves on each element of a top-level Many: its one ``label``. The occurrences
the leaf axis does not reach into, so their elements stay the narrowest records
the workload has however wide the nested ones grow."""

_STAMPS: Final = 1
"""Leaves on the ``stamp`` record each element of the nested Many carries: the
deepest record the workload declares, and the only one a reduction reaches by
descending a Many first. Fixed like :data:`_LABELS`, so widening a leaf moves one
population of records rather than every population at once."""

_VIEWS: Final = ("children", "arms", "extra1", "extra2")
"""The parent's declared relationships, in declaration order. A slot count names
the first ``slots`` of them; the model declares them all at every count, so a
relationship a plan did not use is model-owned metadata and costs no reading.

No two of them JOIN alike, which is what makes their three fan-outs three
different result sets rather than three spellings of one: the broad view gathers
by the child's parent key, which every child fills with its own root's; the
narrowed arm by an arm key only the children it gathers carry; and the two extras
by the child's twin key, which every child fills with a CHILD's key and no root's,
so a level fetching one gathers nothing at all. Four unnarrowed views of one join
would each return every child, and a slot holding fewer would be storage no plan
lays out."""

_TWIN: Final = "twin"
"""The child's own many-to-one, whose slot the plan puts on the source the broad
hop's children were read at. Every one of them names a twin, so every admitted
parent of that hop receives the attachment, exactly as a fan-back writes one."""

_ID_KEY: Final = "id"
_PARENT_KEY: Final = "parentId"
_ARM_KEY: Final = "armId"
_TWIN_KEY: Final = "twinId"
"""The Attributes the plan's hops join through, as the descriptor below spells
them: the primary key a hop resolves a target by, the one the broad hop gathers
children by, the one the narrowed arm gathers its own by, and the one the twin hop
resolves a second projection through. Their stored values are the only Attribute
values that name anything, which is why they are spelled apart from the rest.
What each RELATIONSHIP does with them is the declaration's business and is read
back off it as :data:`_JOIN_KEYS` and by :func:`_unproduced`."""

_CONCRETES: Final = ("Alpha", "Beta")
"""The resolved concretes of the measured family, taken in turn down each
parent's children, and again down the duplicates the twin hop converts — so each
of the two child source levels resolves both of them. That is the sense of
polymorphic that costs a reading anything: two member layouts of different
widths, two merged rows, and a source view row whose width is the source level's
rather than the concrete's, all inside one graph."""


def _document(members: int, leaves: int, ones: int, manys: int) -> Mapping[str, object]:
    """A model descriptor whose Child family carries ``members`` inherited
    Attributes, ``ones`` top-level One Value Objects and ``manys`` top-level Many
    ones, whose nested records carry ``leaves`` each.

    Descriptor-backed rather than class-backed because the axes ARE the member,
    leaf, and occurrence counts: one document generator answers every point of
    the grid, where near-identical class pairs would answer the same question by
    repetition. Nothing here constructs an Entity, so the classes a typed
    materializer would need are not part of what is measured.

    ``Child`` is the ABSTRACT ROOT of a table-per-hierarchy family, so the
    measured level is polymorphic: ``Alpha`` reaches it through the intermediate
    abstract ``Special`` and ``Beta`` descends from the root directly, which
    gives the two concretes different applicable member sets — five positions
    against six at the smallest member count — and therefore different layouts
    and different merged rows, under one source view row a schema interns per
    admitted slot tuple and both of them share. Every member the axes vary is
    declared on the root, so widening one widens both concretes' rows alike and a
    step stays a count of rows rather than of concretes.

    The occurrences are what put a document on the measured path: ``mark`` is a
    top-level One holding a nested One and a nested Many, whose every element
    holds a ``stamp`` of its own; ``marks`` is a top-level Many; and ``spare``
    and ``notes`` are the One and the Many their own axes add. A Many is declared
    at :data:`_ELEMENTS` elements by the rows, so a record count is not a row
    count. Between them those reach every SHAPE the reduction descends: a One and
    a Many occurrence each at the top and nested inside another, and a record
    whose own nested occurrence is reached only by descending a Many. Depth is
    not what makes that complete — ``_structure`` and ``_structure_occurrence``
    call each other with no notion of how deep either is — which is why the tree
    is priced by that same recursion rather than by one more level per reading.
    Which PRESENCE STATE each of those reaches is the rows' business rather than
    the declaration's, and is :data:`_STATES`.

    Every occurrence of One multiplicity, every Value Object leaf, and every
    Attribute but the primary key is declared NULLABLE, which is what makes the
    absent and null spellings of each a conforming stored state instead of a
    ``required-member-absent`` or ``stored-data-attribute-null`` finding: a
    reading of the conforming path can only be taken over documents the read
    contract accepts. A Many declares none, because a Many is never nullable and
    needs no declaration to reach its zero state — the read contract gives its
    omitted and null spellings one empty value at every depth.

    Zero of either count declares no Value Object at all, which is the
    document-free graph the whole-document reading is taken against.

    ``twin`` is the child's own many-to-one back into its family, named by a
    ``twinId`` every child row carries. It is not the inverse of the hop the
    children arrived through — ``parent`` is — so a plan reaching it issues a
    real query rather than resolving the ancestor already in hand, and the rows
    it reads are children the broad hop read already.

    The root's four views join THREE different ways, which is what makes the
    fan-out under one root three different sets of rows rather than one set
    written three times: ``children`` gathers by ``parentId``, which every child
    fills with its own root's key; ``arms`` by ``armId``, which only the children
    that hop gathers carry; and ``extra1`` and ``extra2`` by ``twinId``, which
    every child fills with a CHILD's key and no root's, so each of them is a level
    that gathered a parent and found nothing. Every one of those is an ordinary
    unnarrowed view, so what one returns is its join and nothing else — four views
    of one join would return one another's rows exactly.
    """

    def one_to_many(name: str, gathers_by: str, *, dependent: bool = False) -> dict[str, object]:
        declared: dict[str, object] = {
            "name": name,
            "cardinality": "one-to-many",
            "join": {
                "source": _ID_KEY,
                "target": {"entity": f"{_NAMESPACE}.Child", "attribute": gathers_by},
            },
        }
        if dependent:
            declared["dependent"] = True
        return declared

    def leaf_run() -> list[dict[str, object]]:
        return [
            {"name": f"v{index:02d}", "type": "string", "nullable": True} for index in range(leaves)
        ]

    def label() -> list[dict[str, object]]:
        return [{"name": "label", "type": "string", "nullable": True}]

    value_objects: list[dict[str, object]] = []
    if ones:
        value_objects.append(
            {
                "name": "mark",
                "nullable": True,
                "attributes": label(),
                "valueObjects": [
                    {"name": "inner", "nullable": True, "attributes": leaf_run()},
                    {
                        "name": "inners",
                        "multiplicity": "many",
                        "attributes": leaf_run(),
                        "valueObjects": [
                            {
                                "name": "stamp",
                                "nullable": True,
                                "attributes": [{"name": "at", "type": "string", "nullable": True}],
                            }
                        ],
                    },
                ],
            }
        )
    if manys:
        value_objects.append({"name": "marks", "multiplicity": "many", "attributes": label()})
    if ones > _ONES[0]:
        value_objects.append({"name": "spare", "nullable": True, "attributes": leaf_run()})
    if manys > _MANYS[0]:
        value_objects.append({"name": "notes", "multiplicity": "many", "attributes": label()})

    return {
        "entities": [
            {
                "name": "Parent",
                "namespace": _NAMESPACE,
                "table": "retention_parent",
                "attributes": [{"name": "id", "type": "int64", "primaryKey": True}],
                "relationships": [
                    one_to_many(_VIEWS[0], _PARENT_KEY, dependent=True),
                    one_to_many(_VIEWS[1], _ARM_KEY),
                    *(one_to_many(name, _TWIN_KEY) for name in _VIEWS[2:]),
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
                    {"name": _ID_KEY, "type": "int64", "primaryKey": True},
                    {"name": _PARENT_KEY, "type": "int64", "nullable": True},
                    {"name": _ARM_KEY, "type": "int64", "nullable": True},
                    {"name": _TWIN_KEY, "type": "int64", "nullable": True},
                    *(
                        {
                            "name": f"c{index:02d}",
                            "type": "string",
                            "maxLength": 32,
                            "nullable": True,
                        }
                        for index in range(members - 4)
                    ),
                ],
                "valueObjects": value_objects,
                "relationships": [
                    {"name": "parent", "reverseOf": f"{_NAMESPACE}.Parent.children"},
                    {
                        "name": _TWIN,
                        "cardinality": "many-to-one",
                        "join": {
                            "source": _TWIN_KEY,
                            "target": {"entity": f"{_NAMESPACE}.Child", "attribute": "id"},
                        },
                    },
                ],
                "indices": [{"name": "retention_child_parent", "attributes": [_PARENT_KEY]}],
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


@cache
def _model(members: int, leaves: int, ones: int, manys: int) -> tuple[Metamodel, LayoutCatalog]:
    """One document's accepted model and its layout catalog.

    Keyed by what the DECLARATION varies, which is every workload parameter but
    the stored state: two row sets holding different presence states are two
    fillings of one model, and deriving the model twice would be the only
    expensive thing about a state.
    """
    meta = model_of(domain_model_from_document(_document(members, leaves, ones, manys)))
    return meta, CatalogedModel(meta).layouts


def _join_keys(meta: Metamodel) -> frozenset[str]:
    """Every Attribute of the measured family that some declared hop joins
    through, read off ``meta``'s own relationship metadata.

    Derived rather than restated so the rows and the descriptor cannot drift: a
    join retargeted in the declaration moves what :func:`_child_row` carries
    through a state and what :func:`_unproduced` reads an edge against together.
    The measured family's side alone, because these names select positions in a
    CHILD's row; the root's own end of every one of them is its primary key,
    which is carried for a reason of its own.
    """
    facet = relationship_view(meta)
    child = _identity(meta, "Child")
    return frozenset(
        endpoint.name
        for entity in (_identity(meta, "Parent"), child)
        for declared in facet.relationships(entity) or ()
        for endpoint in (declared.join.source, declared.join.target)
        if endpoint.entity == child
    )


_JOIN_KEYS: Final = _join_keys(_model(_MEMBERS[0], _LEAVES[0], _ONES[0], _MANYS[0])[0])
"""The join Attributes, carried in every stored state beside the primary key and
alone among the rest of them. Taken off the smallest declaration because every
point declares the identical relationships; only the Attribute and Value Object
counts move.

What a hop RETURNS is derived from these values, so a row holding one of them
zero is not this graph in another state but a different graph: a child whose
``parentId`` is null or absent is not a row the broad hop's query gathers under
any parent, and one whose ``twinId`` is names no target for the twin hop to
resolve, while the fan-out written above it would still hold both edges. A
child's ``armId`` is null exactly where the narrowed arm does not gather it, so
zeroing that population is what would make the arm's own axis unproducible. Every
other Attribute is nullable and reaches both zero spellings, which is what covers
the Attribute position's admitted states without leaving the composed graph a
topology no plan produces.

The primary key is in here too — it is a join target, and the twin hop resolves
against it — and changes nothing, because :func:`_child_row` answers a key before
it reads this set."""


class _Stored(NamedTuple):
    """Which of a row's declared members hold their ZERO value, and how that zero
    is spelled.

    `python.md`'s *Value Object member rows* closes what a position may hold: an
    occurrence slot admits ``ABSENT | None | row`` for a One and ``ABSENT |
    tuple[row, ...]`` for a Many, and a leaf position admits its decoded value or
    ``ABSENT`` where the stored document did not carry it, with ``None`` for a
    stored null. A fully carried document reaches only the populated half of
    those sets, so which members are stored zero is a parameter of the WORKLOAD
    rather than of the declaration — the same model, filled differently.

    ``rank`` names the nesting rank whose occurrences are stored zero, counted off
    the occurrence's own identity path: a top-level occurrence is rank 0 and an
    occurrence declared inside a record of rank ``r`` is rank ``r + 1``. By rank
    rather than by name because a zeroed occurrence reduces to nothing for
    anything below it to sit in, so one rank at a time is the coarsest grouping
    that can still reach every rank the declaration has.

    ``leaves`` and ``attributes`` zero the two populations that are not
    occurrences: every Value Object leaf at every depth, and every Entity
    Attribute that neither identifies a row nor joins one to another, which is
    :data:`_JOIN_KEYS`.

    ``omitted`` is the spelling — the stored document has no key for the member,
    rather than a key holding JSON null. The two spellings are ONE state wherever
    the read contract collapses them: a top-level occurrence reads an absent
    column and a null one through the same ``SqlNull`` carrier, and a Many's
    omitted and null spellings are one zero value at every depth
    (`m-snapshot-read` *What a materialized value carries*). They are two states
    for a nested One and for a leaf, which read ``ABSENT`` for the first and
    ``None`` for the second.
    """

    rank: int | None = None
    leaves: bool = False
    attributes: bool = False
    omitted: bool = False


_CARRIED: Final = _Stored()
"""Every declared member carried at every depth: the state the crossed grid, all
four document steps, and the row calibration are read at."""


def _zeroed(declared: ValueObjectMetadata | NestedValueObjectMetadata, stored: _Stored) -> bool:
    """Whether ``stored`` holds ``declared``'s occurrence in its zero value."""
    return stored.rank == len(declared.identity.path) - 1


class _Point(NamedTuple):
    """One workload the readings are stated over: ``members`` Attributes the
    family root declares, ``slots`` relationship views its root-parented levels
    declare, ``arms`` projection references in the narrowed view of them,
    ``leaves`` on each nested Value Object record, ``elements`` in each Many
    occurrence, ``ones`` and ``manys`` top-level Value Objects of each
    multiplicity on each child projection, and the ``stored`` state the rows hold
    those declarations in.

    ``projected`` is the one parameter that is a fact about the READ rather than
    about the model or the rows: a read whose resolved position carries no
    document column leaves every top-level occurrence position ``ABSENT``,
    whatever the row underneath it stores. It is therefore outside
    :attr:`shape`, which two points share exactly when they convert the same
    rows against the same model.

    ``slots`` is outside it for the opposite reason and is the only other
    parameter that is: how many views a plan declares is a fact about the plan,
    and moves no row at all. ``arms`` is inside, because the arm's fan-out is
    what its own join returns and that is a property of the rows.

    The crossed grid pins everything after ``arms``; each of the four document
    steps moves exactly one of the four counts; and each state point moves
    ``stored`` or ``projected`` alone.
    """

    members: int
    slots: int
    arms: int
    leaves: int = _LEAVES[0]
    elements: int = _ELEMENTS[0]
    ones: int = _ONES[0]
    manys: int = _MANYS[0]
    stored: _Stored = _CARRIED
    projected: bool = True

    @property
    def shape(self) -> tuple[int, int, int, int, int, int, _Stored]:
        """The model and rows this point converts, which is what the axes moving
        a document share and the slot axis does not."""
        return (
            self.members,
            self.arms,
            self.leaves,
            self.elements,
            self.ones,
            self.manys,
            self.stored,
        )


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
_WIDER_ONES: Final = _LEAST._replace(ones=_ONES[1])
_WIDER_MANYS: Final = _LEAST._replace(manys=_MANYS[1])
"""The second point of each document step. One axis moves and six stand still,
which is what lets each step name one population of the document rather than a
mixture of them."""

_BARE: Final = _LEAST._replace(ones=0, manys=0)
"""The same graph with no Value Object declared at all.

The baseline every whole-document reading is taken against, and the only point
that is neither a grid point, the far end of a document step, nor a state of the
widest document. What separates it from a point that declares one is every record
that declaration names at every depth, which is what turns the reading into an
exact TOTAL: a step prices the population it moves and absorbs every population
it holds still, and an occurrence nested inside another one is held still by
every axis this suite has."""

_DOCUMENTS: Final = (_LEAST, _WIDER_LEAVES, _WIDER_ELEMENTS, _WIDER_ONES, _WIDER_MANYS)
"""Every point a document step is read at, which is every point the total is read
at with its members carried."""

_WIDEST: Final = _LEAST._replace(ones=_ONES[1], manys=_MANYS[1])
"""Both occurrence axes at their far ends at once, which is the declaration whose
sites are the union of every other point's.

Where the states are read, so a state reading covers a top-level One and a
top-level Many that nest something and a pair that nest nothing, rather than
whichever of them one step happened to add."""


def _declared(point: _Point) -> tuple[ValueObjectMetadata, ...]:
    """The top-level occurrences the measured level declares at ``point``.

    Read off one concrete because every occurrence the workload declares is
    declared on the family root, so the two concretes carry the identical
    occurrence tree and differ only in Attributes.
    """
    meta, catalog = _model(point.members, point.leaves, point.ones, point.manys)
    return catalog.entity(_identity(meta, _CONCRETES[0])).occurrences


def _ranks(declared: Sequence[ValueObjectMetadata | NestedValueObjectMetadata]) -> frozenset[int]:
    """Every nesting rank the occurrences under ``declared`` reach."""
    return frozenset[int]().union(
        *(
            {len(occurrence.identity.path) - 1, *_ranks(occurrence.value_objects)}
            for occurrence in declared
        )
    )


_RANKS: Final = tuple(sorted(_ranks(_declared(_WIDEST))))
"""The nesting ranks the measured declaration reaches, taken off the declaration
rather than enumerated by hand: a document nested one level deeper grows this
tuple, and the states below with it."""

_STATES: Final = (
    _CARRIED,
    *(_Stored(rank=rank, omitted=omitted) for rank in _RANKS for omitted in (False, True)),
    *(_Stored(leaves=True, omitted=omitted) for omitted in (False, True)),
    *(_Stored(attributes=True, omitted=omitted) for omitted in (False, True)),
)
"""Every stored state the widest document is measured in.

Generated rather than listed: one state per (population, spelling), where the
populations are the occurrence ranks the declaration reaches plus the leaves and
the Attributes, and the spellings are the two a stored document has. What makes
the set CLOSED is not this construction but its consequence — the union of the
states it puts each kind of position in is exactly :data:`_ADMITTED_STATES`,
asserted by
:func:`test_every_measured_position_reaches_every_state_its_contract_admits`
rather than argued here."""

_STATE_POINTS: Final = (
    *(_WIDEST._replace(stored=stored) for stored in _STATES),
    _WIDEST._replace(projected=False),
)
"""Where the state readings are taken: the widest document in each stored state,
and once more with its column not projected at all — the one way a TOP-LEVEL
position reads ``ABSENT``, which no stored document can produce because an absent
column and a null one are one carrier."""


class _Workload(NamedTuple):
    """One shape's whole model and its rows, formed once at import.

    Every row a window converts is allocated out here, which is what excludes
    decoded payload leaves from the readings STRUCTURALLY rather than by
    filtering: a compact row that merely references one of these values costs the
    reading the position and not the value.

    ``levels`` is the resolved concrete each child position is read at, in
    position order, so a conversion takes the exact Entity's own layout exactly
    as a polymorphic level's compiled read hands one over per row. ``unread`` is
    the same levels resolved by a read that projected no document column, which
    is what a point measures the unprojected state through.
    """

    meta: Metamodel
    parent: LevelContext
    levels: tuple[LevelContext, ...]
    unread: tuple[LevelContext, ...]
    views: tuple[RelationshipViewKey, ...]
    twin: RelationshipViewKey
    parents: tuple[dict[str, object], ...]
    children: tuple[tuple[dict[str, object], ...], ...]


def _workload(
    members: int, arms: int, leaves: int, elements: int, ones: int, manys: int, stored: _Stored
) -> _Workload:
    meta, catalog = _model(members, leaves, ones, manys)
    parent, child = _identity(meta, "Parent"), _identity(meta, "Child")
    concretes = tuple(_level(catalog.entity(_identity(meta, name))) for name in _CONCRETES)
    levels = tuple(concretes[index % len(_CONCRETES)] for index in range(_CHILDREN))
    return _Workload(
        meta,
        _level(catalog.entity(parent)),
        levels,
        tuple(LevelContext(level.layout, ()) for level in levels),
        tuple(RelationshipViewKey(RelationshipIdentity(parent, name)) for name in _VIEWS),
        RelationshipViewKey(RelationshipIdentity(child, _TWIN)),
        tuple({"id": 1_000 + cell} for cell in range(_LARGER)),
        tuple(
            tuple(
                _child_row(levels[index].layout, arms, elements, stored, cell, index)
                for index in range(_CHILDREN)
            )
            for cell in range(_LARGER)
        ),
    )


def _child_row(
    layout: EntityLayout, arms: int, elements: int, stored: _Stored, cell: int, index: int
) -> dict[str, object]:
    """One child's stored row, keyed as its concrete's own storage names and
    filled to ``stored``.

    The primary key and the join Attributes are carried in every state, alone
    among the Attributes, and for the same kind of reason. A row whose key is
    absent or null is a ``stored-data-primary-key-null`` projection that merges
    with nothing, which is the non-conforming path rather than a presence state of
    the conforming one; a row whose join key is either is one no hop of this plan
    would have gathered, which is :data:`_JOIN_KEYS`.
    """
    tag = f"{cell}-{index}"
    row: dict[str, object] = {}
    for attribute in layout.attributes:
        if isinstance(attribute.primary_key, PrimaryKey):
            row[attribute.storage.name] = 10_000 + cell * 100 + index
        elif attribute.identity.name in _JOIN_KEYS or not stored.attributes:
            row[attribute.storage.name] = _attribute_value(attribute, arms, cell, index, tag)
        elif not stored.omitted:
            row[attribute.storage.name] = None
    for occurrence in layout.occurrences:
        name = occurrence.storage.name
        if not _zeroed(occurrence, stored):
            row[name] = _stored_occurrence(occurrence, elements, stored, f"{name}-{tag}")
        elif not stored.omitted:
            row[name] = None
    return row


def _attribute_value(
    attribute: AttributeMetadata, arms: int, cell: int, index: int, tag: str
) -> object:
    """One Attribute's carried stored value, spelled by its declared Neutral Type.

    The join Attributes are answered before the types, because what they hold is
    what each hop's query returns. Every child's ``parentId`` is its own cell's
    root, so the broad hop gathers all of them; its ``armId`` is that same root
    for the first ``arms`` of them and null for the rest, so the narrowed arm
    gathers exactly those and cannot reach one more; and its ``twinId`` is one of
    the duplicates the twin hop converts a second time — which is what makes that
    hop a real fetch level over rows the broad hop read already rather than a
    second spelling of the same projection, and what leaves the two views joining
    against it empty, since no root's key is a child's.
    """
    if attribute.identity.name == _PARENT_KEY:
        return 1_000 + cell
    if attribute.identity.name == _ARM_KEY:
        return 1_000 + cell if index < arms else None
    if attribute.identity.name == _TWIN_KEY:
        return 10_000 + cell * 100 + index % _DUPLICATES
    if isinstance(attribute.type, Int64):
        return 10_000 + cell * 100 + index
    if isinstance(attribute.type, Float64):
        return float(index)
    return f"{attribute.identity.name}-{tag}"


def _stored_occurrence(
    declared: ValueObjectMetadata | NestedValueObjectMetadata,
    elements: int,
    stored: _Stored,
    tag: str,
) -> object:
    """The document ``declared`` holds under ``stored``: a Many stores
    ``elements`` element documents and a One stores a single document.

    Reduced from the declaration rather than written out, so the rows a workload
    converts and the price :func:`_occurrence_price` charges walk one tree by one
    recursion and a declaration nobody thought to fill cannot exist.
    """
    if declared.multiplicity is Multiplicity.MANY:
        return [
            _stored_record(declared, elements, stored, f"{tag}-{element}")
            for element in range(elements)
        ]
    return _stored_record(declared, elements, stored, tag)


def _stored_record(
    declared: ValueObjectMetadata | NestedValueObjectMetadata,
    elements: int,
    stored: _Stored,
    tag: str,
) -> dict[str, object]:
    """One record's stored document: every declared leaf, then every nested
    occurrence, each of them carried or spelled zero.

    Nothing here consults a leaf's type because every Value Object leaf the
    workload declares is a string.
    """
    document: dict[str, object] = {}
    for leaf in declared.attributes:
        if not stored.leaves:
            document[leaf.identity.name] = f"{leaf.identity.name}-{tag}"
        elif not stored.omitted:
            document[leaf.identity.name] = None
    for nested in declared.value_objects:
        name = nested.identity.path[-1]
        if not _zeroed(nested, stored):
            document[name] = _stored_occurrence(nested, elements, stored, f"{name}-{tag}")
        elif not stored.omitted:
            document[name] = None
    return document


_POINTS: Final = (*_GRID, *_DOCUMENTS, *_STATE_POINTS, _BARE)
"""Every point this suite measures anything at: the crossed grid, the far end of
each document step, the widest document in each state its positions admit, and
the document-free baseline the totals are taken against."""

_SHAPES: Final = tuple(dict.fromkeys(point.shape for point in _POINTS))
"""What the models and their rows are formed at, taken off the points that read
them rather than listed beside them, so a point and the workload it names cannot
drift apart."""

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

_LEAF_POOL: Final = tuple(f"leaf-{index:02d}" for index in range(max(_LEAVES) + _LABELS))
"""Leaves the row calibration fills its rows from, allocated out here for the
reason every workload row is: what it prices is the row, not the values in it."""

_ROWS: Final = (256, 512)
"""Rows the calibration holds, at two counts, so what it reads is the marginal
cost of one row rather than a total carrying whatever else the seam allocated."""


def _slot_table(point: _Point) -> tuple[tuple[ChildSlot, ...], ...]:
    """The table ``handle/_read._slot_table`` yields for this workload's plan,
    dense by source level.

    The plan descends the broad ``children`` hop first and the ``twin`` hop
    directly under it, then the root's remaining views — the narrowed arm, and
    however many gathered nothing. So ``twin`` is plan level 1 and reads its
    duplicates at source 2, and every level after it attaches to the root. A
    level's slot lands on whichever source its OWN parents came from, so every
    root-parented level's slot is on entry 0 and ``twin``'s is on entry 1, and
    every entry after those is empty because a level owns an entry whether or not
    anything attaches beneath it.

    Every source level carries a slot tuple no other source shares, which is what
    makes the reading exact about where a view row is stored: the twin slot is on
    entry 1 and every projection read at that source receives it, while the
    duplicates read at source 2 carry none. A table that put both populations on
    one source would hand the duplicates a twin position no plan of theirs writes.
    """
    return (
        tuple(ChildSlot(view) for view in _WORKLOADS[point.shape].views[: point.slots]),
        (ChildSlot(_WORKLOADS[point.shape].twin),),
        *(() for _ in range(point.slots)),
    )


def _compose(point: _Point, cells: int) -> tuple[SnapshotGraph, GraphMerge]:
    """One whole materialization of ``cells`` cells, built and merged the way a
    read builds and merges one: a fresh slot table and view schema per execution,
    every row converted through the production converter under the concrete its
    own level resolved it to, the builder dropped at sealing, and the sealed graph
    and its merge the only things that come back.

    Each view holds what its own join returns and nothing else: the broad hop
    every child of the cell, the narrowed arm the children whose arm key names
    that root, and each remaining view nothing at all.
    :func:`test_every_view_the_graph_records_holds_exactly_what_its_own_join_produces`
    is what holds this to that, so the prefix here is a consequence of the rows
    rather than a choice made beside them.

    ``point.projected`` selects which resolved level each child row converts
    under, because that is where a read states which document columns its
    position carried."""
    workload = _WORKLOADS[point.shape]
    levels = workload.levels if point.projected else workload.unread
    views = workload.views[: point.slots]
    builder = GraphBuilder(ViewSchema(_slot_table(point)))
    roots: list[int] = []
    for cell in range(cells):
        parent = convert_row(workload.parents[cell], workload.parent, builder, source=_ROOT_SOURCE)
        children = tuple(
            convert_row(row, level, builder, source=_BROAD_SOURCE)
            for row, level in zip(workload.children[cell], levels, strict=True)
        )
        twins = tuple(
            convert_row(
                workload.children[cell][index],
                levels[index],
                builder,
                source=_TWIN_SOURCE,
            )
            for index in range(_DUPLICATES)
        )
        builder.write_view(parent, views[0], children)
        builder.write_view(parent, views[1], children[: point.arms])
        for empty in views[2:]:
            builder.write_view(parent, empty, ())
        for index, child in enumerate(children):
            builder.write_view(child, workload.twin, twins[index % _DUPLICATES])
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
    read it — the smallest point is the baseline all four document steps are
    taken against."""
    tracemalloc.start()
    try:
        return retained(seam(point, cells))
    finally:
        tracemalloc.stop()


def _step(
    seam: Callable[[_Point, int], Seam], wide: _Point, cells: int, base: _Point = _LEAST
) -> int:
    """What moving from ``base`` to ``wide`` costs ``seam``.

    Read as a two-point difference rather than off the crossed grid, for the
    reason :data:`_LEAVES` states: every other axis holds the same value at both
    points, so the whole of what moves between them is the one the caller varied.
    A step over one document axis leaves ``base`` at :data:`_LEAST`; the total
    takes it from :data:`_BARE`, where the axes are not one apart but the whole
    document is.
    """
    return _at(seam, wide, cells) - _at(seam, base, cells)


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
    itself, plus one pointer for each position it holds.

    A row of no positions costs NOTHING rather than :data:`_EMPTY_ROW`, because
    the interpreter answers every one of them with a single shared object — which
    is the object a zero-element Many occurrence reduces to, so this is what makes
    that state free rather than a row wide."""
    return _EMPTY_ROW + positions * _POINTER if positions else 0


def _element_bytes(leaves: int) -> int:
    """What one more element in every Many occurrence costs one child projection:
    the ``inners`` element's own record — its leaves and the position naming the
    ``stamp`` its declaration nests under it — that ``stamp`` record itself, and
    the position naming the element in the occurrence's row; plus the same for
    ``marks``, whose elements carry the one ``label`` and nothing below it however
    wide the nested records grow.

    A representation charging anything per RECORD — the pre-cutover graph held a
    ``ValueObjectRecord`` for each — charges it three times more here, which is
    what this reading is stated exactly enough to refuse.
    """
    return _row_bytes(leaves + 1) + _row_bytes(_STAMPS) + _row_bytes(_LABELS) + 2 * _POINTER


def _one_occurrence_bytes(leaves: int) -> int:
    """What one more top-level ONE occurrence costs one child projection: the
    position it takes in the member row after the Attributes, and the one record
    that position holds.

    A representation charging anything per OCCURRENCE — the pre-cutover graph held
    a ``ValueObjectOccurrenceInput`` for each — is a term this reading has and the
    element and leaf steps do not, because their populations move underneath a
    fixed number of occurrences.
    """
    return _POINTER + _row_bytes(leaves)


def _many_occurrence_bytes(elements: int) -> int:
    """What one more top-level MANY occurrence costs one child projection: the
    position in the member row, the occurrence's own row of element positions, and
    one record per element — each of them carrying the single ``label`` a
    workload Many declares.

    Read separately from the One because the reduction is separate: the Many
    branch structures a row per element where the One branch structures one row or
    none, so a cost that returned to one branch alone would leave the other's step
    exactly where it is.
    """
    return _POINTER + _row_bytes(elements) + elements * _row_bytes(_LABELS)


def _occurrence_price(
    declared: ValueObjectMetadata | NestedValueObjectMetadata, elements: int, stored: _Stored
) -> int:
    """What one whole occurrence of ``declared`` costs under ``stored``, every
    record under it included.

    The recursion :func:`~parallax.snapshot.materialize._convert._structure_occurrence`
    reduces one by, priced instead of walked: a Many is a row of element positions
    holding one record per element, a One is a single record, and a record is its
    own positional row plus whatever its nested occurrences cost. Depth is not a
    parameter for the same reason it is not one there — the two branches call each
    other, and neither knows how deep it is — so this prices whatever tree a
    declaration names rather than the depth some reading happened to reach.

    An occurrence ``stored`` holds in its zero value costs NOTHING at all, and
    nothing under it exists to cost anything: that branch reduces to ``None`` for
    a One and to the interpreter's shared empty tuple for a Many, and neither is
    an allocation. The position naming it stays charged, by the row that holds
    it — which is what makes a zero state a state of the SAME row rather than a
    narrower one.
    """
    if _zeroed(declared, stored):
        return 0
    if declared.multiplicity is Multiplicity.MANY:
        return _row_bytes(elements) + elements * _record_price(declared, elements, stored)
    return _record_price(declared, elements, stored)


def _record_price(
    declared: ValueObjectMetadata | NestedValueObjectMetadata, elements: int, stored: _Stored
) -> int:
    """What one reduced record of ``declared`` costs: the positional row holding
    its leaves and then its nested occurrences, and every occurrence those later
    positions name.

    ``stored`` reaches this only through the occurrences: a leaf position costs
    its pointer whether it holds a decoded value, ``None``, or ``ABSENT``, so the
    two zero states of a leaf are exactly as wide as the carried one.
    """
    return _row_bytes(len(declared.attributes) + len(declared.value_objects)) + sum(
        _occurrence_price(nested, elements, stored) for nested in declared.value_objects
    )


def _document_bytes(point: _Point, cells: int) -> int:
    """What the whole Value Object half of a ``cells``-cell graph may cost, priced
    from the declaration and ``point``'s stored state rather than read off the
    graph: per projection the workload converts, one position in its member row
    per top-level occurrence plus the subtree that position holds.

    An unprojected read holds every one of those subtrees at nothing — the
    position reads ``ABSENT`` whatever the row beneath it stores — so what is left
    is the positions alone, which is the floor a declared document can cost.

    Summed over the levels a cell converts — the parent, every child, and the
    duplicates the twin hop reads again — rather than over a count of rows, so
    two concretes declaring different occurrences would be priced apart rather
    than assumed alike."""
    workload = _WORKLOADS[point.shape]
    projections = tuple(
        sum(
            _POINTER
            + (_occurrence_price(declared, point.elements, point.stored) if point.projected else 0)
            for declared in level.layout.occurrences
        )
        for level in (workload.parent, *workload.levels)
    )
    root, children = projections[0], projections[1:]
    return cells * (root + sum(children) + sum(children[:_DUPLICATES]))


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


_UNDECLARED: Final = object()
"""What a row holds at an Attribute its own Entity does not declare, which is not
a value and matches nothing. A join names one Attribute of one Entity, so every
projection of another family answers this rather than a position."""


def _stored_at(
    layout: EntityLayout, row: tuple[object, ...], attribute: AttributeIdentity
) -> object:
    """What ``row`` holds at ``attribute``, found by position because a member row
    carries no key beside a value, and :data:`_UNDECLARED` where this projection's
    Entity declares no such Attribute at all.

    By Identity rather than by name: a layout carries every applicable Attribute
    under the Identity of the Entity that DECLARED it, so ``Parent.id`` and
    ``Child.id`` are two Attributes here exactly as they are two columns in
    storage, and a join through one of them reaches only its own family's rows.
    """
    return next(
        (
            row[position]
            for position, declared in enumerate(layout.attributes)
            if declared.identity == attribute
        ),
        _UNDECLARED,
    )


def _edges(value: object) -> tuple[int, ...]:
    """The projections one view position names: a to-many arm's whole tuple, a
    to-one's single index, and none at all where no level wrote the slot."""
    if isinstance(value, tuple):
        return cast("tuple[int, ...]", value)
    return () if value is ABSENT else (cast("int", value),)


def _nodes(rows: GraphRows, projections: Sequence[int]) -> tuple[int, ...]:
    """``projections`` as the logical nodes they merge onto, in ascending order.

    Sorted and by NODE because that is the granularity a returned row has once the
    graph holds it: the same stored row read at two source levels is one node, so
    a hop that reached it through either has returned the same thing, and the
    order a to-many result arrives in is the declared ``orderBy``'s business
    rather than this reading's. Duplicates are kept, so a fan-out naming one node
    twice is a fan-out no single-pass query returned.
    """
    return tuple(sorted(rows.logical_ids[projection] for projection in projections))


def _produced(rows: GraphRows, target: AttributeIdentity, held: object) -> tuple[int, ...]:
    """Every logical node a relationship query matching ``target`` against
    ``held`` returns, read off the graph's own rows.

    A join returns the rows whose target Attribute EQUALS the value the holding
    row joins from, so a null, absent, or undeclared value on either side returns
    nothing at all — none of the three is a value anything equals. One node per
    matching row: a duplicate the twin hop read a second time is the same row
    matched once, not a second row to return.
    """
    if held is None or held is ABSENT or held is _UNDECLARED:
        return ()
    return tuple(
        sorted(
            {
                rows.logical_ids[projection]
                for projection, layout in enumerate(rows.layouts)
                if _stored_at(layout, rows.member_rows[projection], target) == held
            }
        )
    )


def _unproduced(rows: GraphRows, meta: Metamodel) -> list[tuple[int, str, tuple[int, ...]]]:
    """Every view position holding something other than exactly the fan-out its
    own relationship's join produces, as the projection holding the view, the
    relationship, and the nodes the join would have returned.

    What a relationship query returns is every row whose target Attribute matches
    the source's, so a recorded edge between two rows that do not match is storage
    no plan lays out — and so is a MISSING one, which is the half a per-edge check
    cannot see: four views of one join return one another's rows exactly, and any
    two of them holding different sets is a graph no execution produced, however
    conforming each row is on its own and however exactly the arithmetic prices
    the positions. Both halves are the one comparison here, because both are the
    same question asked of a set rather than of an edge.

    Read off the sealed graph and the accepted model, never off the composition
    that wrote the views: the joins come from ``meta``'s own relationship
    metadata, so a fixture that retargets one and a fan-out that did not follow it
    disagree here.

    What it can see is bounded by the graph: the candidate rows are the ones the
    graph holds, so a row a query would have returned and nothing converted at all
    is outside it. The population assertion beside every call is what pins that —
    the graph holds every row the workload has.
    """
    facet = relationship_view(meta)
    unproduced: list[tuple[int, str, tuple[int, ...]]] = []
    for holder, layout in enumerate(rows.layouts):
        for slot, view in enumerate(rows.schema.source(rows.sources[holder], layout).slots):
            declared = facet.relationship(view.relationship)
            assert declared is not None, view
            held = _stored_at(layout, rows.member_rows[holder], declared.join.source)
            produced = _produced(rows, declared.join.target, held)
            if _nodes(rows, _edges(rows.view_rows[holder][slot])) != produced:
                unproduced.append((holder, view.relationship.name, produced))
    return unproduced


_ATTRIBUTE_POSITION: Final = "Entity Attribute"
_LEAF_POSITION: Final = "Value Object leaf"
_OCCURRENCE_POSITION: Final = {
    (True, Multiplicity.ONE): "top-level One occurrence",
    (True, Multiplicity.MANY): "top-level Many occurrence",
    (False, Multiplicity.ONE): "nested One occurrence",
    (False, Multiplicity.MANY): "nested Many occurrence",
}
"""The four occurrence positions a presence state is closed at separately: the two
multiplicities reduce through separate branches, and a top-level occurrence is the
only member a READ can decline to carry."""

_ADMITTED_STATES: Final = {
    _ATTRIBUTE_POSITION: frozenset({"carried", "null", "absent"}),
    _LEAF_POSITION: frozenset({"carried", "null", "absent"}),
    _OCCURRENCE_POSITION[True, Multiplicity.ONE]: frozenset({"carried", "null", "absent"}),
    _OCCURRENCE_POSITION[True, Multiplicity.MANY]: frozenset({"carried", "empty", "absent"}),
    _OCCURRENCE_POSITION[False, Multiplicity.ONE]: frozenset({"carried", "null", "absent"}),
    _OCCURRENCE_POSITION[False, Multiplicity.MANY]: frozenset({"carried", "empty"}),
}
"""Every state a conforming read leaves each kind of position in, which is what
makes :data:`_STATES` a closed set rather than a list of states someone thought
of.

`python.md`'s *Value Object member rows* fixes the document rows directly: a One
position admits ``ABSENT | None | row``, a Many admits ``ABSENT |
tuple[row, ...]`` — where the tuple may hold no element — and a leaf holds its
decoded value, ``None`` for a stored null, or ``ABSENT`` where the stored
document did not carry it. An Entity Attribute position reads the same three, by
the same rule one position lower.

A NESTED Many is the one position that does not reach its whole admitted set, and
not for want of a state to store: `python.md`'s *Value Objects* makes a Many's
omitted and null spellings one zero value ``()`` at every nesting depth, so
nothing a stored document holds leaves one ``ABSENT``. What does is a read that
did not carry the member at all, and only a TOP-LEVEL occurrence has that — a
nested one is carried exactly when the record around it is."""


def _state_of(value: object, *, many: bool) -> str:
    """Which of the admitted states ``value`` is in at its own position."""
    if value is ABSENT:
        return "absent"
    if value is None:
        return "null"
    if many and value == ():
        return "empty"
    return "carried"


class _Position(NamedTuple):
    """One position a converted member row holds at whatever depth: which KIND of
    position it is, the ``value`` at it, and the ``state`` that value puts it
    in."""

    kind: str
    value: object
    state: str


def _positions(layout: EntityLayout, row: tuple[object, ...]) -> Iterator[_Position]:
    """Every position one projection's member row holds: its Attributes in the
    layout's order, then each top-level occurrence and everything under it.

    The one walk of a reduced row this suite has, and one rather than two on
    purpose. The census the state readings rest on and the control claimed to
    cover that census are both read off it —
    :func:`test_every_measured_position_reaches_every_state_its_contract_admits`
    takes each position's state and :func:`_zero_state_wrapping_seam` takes the
    value at every position in a state other than carried — so a position either
    of them reaches is one the other reaches, and a declaration or state that
    widened the proof without widening its control cannot exist. Sharing costs
    that control nothing, because what it has to be able to contradict is the
    PRICE those readings are stated against, which :func:`_document_bytes`
    derives from the declaration and not from any walk of a row.
    """
    for cell in row[: layout.attribute_count]:
        yield _Position(_ATTRIBUTE_POSITION, cell, _state_of(cell, many=False))
    for position, declared in enumerate(layout.occurrences, start=layout.attribute_count):
        yield from _occurrence_positions(row[position], declared, top_level=True)


def _occurrence_positions(
    value: object,
    declared: ValueObjectMetadata | NestedValueObjectMetadata,
    *,
    top_level: bool,
) -> Iterator[_Position]:
    """``value``'s own occurrence position, and every position under it,
    descending a Many by its elements and a One by its single record.

    An occurrence holding a zero value ends the descent rather than yielding what
    is under it, because nothing is: that branch reduced to ``None``, ``ABSENT``,
    or the shared empty tuple, and a position it might have held exists in the
    declaration alone.
    """
    many = declared.multiplicity is Multiplicity.MANY
    state = _state_of(value, many=many)
    yield _Position(_OCCURRENCE_POSITION[top_level, declared.multiplicity], value, state)
    if state != "carried":
        return
    rows = cast("tuple[tuple[object, ...], ...]", value if many else (value,))
    for row in rows:
        for cell in row[: len(declared.attributes)]:
            yield _Position(_LEAF_POSITION, cell, _state_of(cell, many=False))
        for offset, nested in enumerate(declared.value_objects, start=len(declared.attributes)):
            yield from _occurrence_positions(row[offset], nested, top_level=False)


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
    # The broad child source level resolves both concretes of one family; their
    # member layouts are different objects of different widths, so a per-row cost
    # is charged against two layouts rather than one; both are laid out and merged
    # by the one execution-owned schema; and a duplicate of either merges onto the
    # logical node its broad projection already made, which is what keeps the
    # projection and logical-node counts above apart.
    graph, merge = _compose(_LEAST, _CELLS)
    rows = graph_rows(graph)
    children = [
        layout
        for layout, source in zip(rows.layouts, rows.sources, strict=True)
        if source == _BROAD_SOURCE
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


def test_every_planned_level_owns_a_source_of_its_own_and_writes_every_slot_it_declares() -> None:
    # `python.md`'s "Execution-owned view slots", as the two facts the slot
    # arithmetic below depends on. A schema fixes one slot tuple per (source
    # level, resolved concrete), where the source level is the plan level that
    # produced the projection, and `handle/_read` converts plan level `i` at
    # source `i + 1` — so no two levels share a source, and the twin hop's
    # duplicates are laid out by their own level's row rather than by the broad
    # hop's. A fan-back then writes its level's view to every admitted parent, so
    # every declared position is one some level fills. Both matter because the
    # readings below count positions: a graph that gave a projection a slot no
    # plan of its own attaches would be charged for storage production never lays
    # out, and the arithmetic would agree with it. What those slots HOLD is the
    # next test's claim.
    for point in (_LEAST, _GRID[-1]):
        graph, _ = _compose(point, _CELLS)
        rows = graph_rows(graph)
        cell = (_ROOT_SOURCE, *(_BROAD_SOURCE,) * _CHILDREN, *(_TWIN_SOURCE,) * _DUPLICATES)
        assert rows.sources == cell * _CELLS, point
        assert {
            source: len(rows.schema.source(source, layout).slots)
            for layout, source in zip(rows.layouts, rows.sources, strict=True)
        } == {_ROOT_SOURCE: point.slots, _BROAD_SOURCE: 1, _TWIN_SOURCE: 0}, point
        assert all(value is not ABSENT for row in rows.view_rows for value in row), point


def test_every_view_the_graph_records_holds_exactly_what_its_own_join_produces() -> None:
    # What makes the fan-out the readings price a topology a plan could have
    # produced rather than one this module wrote by hand. `_compose` writes each
    # view because the workload says a hop gathered those rows, and what a
    # relationship query gathers is every row whose join Attribute matches the
    # source's — no more, which refuses an edge between two rows that do not
    # match, and no fewer, which refuses a view holding a SUBSET of what its join
    # returns. The second half is the one that needs a whole view to state: three
    # of these four views hold different sets of children, and they may only
    # because no two of them join alike. Read at every point the suite measures
    # anything at, the states above all: what a state moves is the rows the
    # fan-out over them was joined from, so a zeroing that reached a join key
    # would leave the relationships standing and unproducible, and every byte
    # reading taken over them exact. The projection count is asserted in the same
    # walk, because the rows the graph holds are the rows a join is checked
    # against: a workload that converted fewer would narrow what a query could
    # have returned to whatever it recorded.
    for point in _POINTS:
        graph, _ = _compose(point, _CELLS)
        rows = graph_rows(graph)
        assert len(rows.layouts) == _CELLS * (1 + _CHILDREN + _DUPLICATES), point
        assert _unproduced(rows, _WORKLOADS[point.shape].meta) == [], point


def test_every_measured_position_reaches_every_state_its_contract_admits() -> None:
    # What makes the state readings below a SWEEP rather than two more points.
    # Declaration shape and presence state are the two things a reduced document
    # varies, and the axes and the total close the first one only: they move how
    # many occurrences, records, and positions a projection has, never what those
    # positions hold. This is the second closed, and it is closed by assertion —
    # the union of the states `_STATES` puts each kind of position in is exactly
    # the set `python.md` admits for that kind, so a state outside it would fail
    # here rather than sit unmeasured. Conformance is asserted in the same walk
    # and for the same reason: the claim is about the CONFORMING path, so every
    # one of these rows has to be one the read contract accepts, and a stored
    # spelling that recorded an issue would be a different claim. That these rows
    # still produce the graph composed over them — that no state zeroed a value an
    # edge was joined from — is the test above, over these points among all the
    # others.
    reached: dict[str, set[str]] = {}
    for point in _STATE_POINTS:
        graph, merge = _compose(point, _CELLS)
        rows = graph_rows(graph)
        assert not any(rows.issues), point
        assert not merge.has_issues, point
        for layout, row in zip(rows.layouts, rows.member_rows, strict=True):
            for position in _positions(layout, row):
                reached.setdefault(position.kind, set()).add(position.state)
    assert {kind: frozenset(states) for kind, states in reached.items()} == _ADMITTED_STATES


def test_a_positional_row_costs_the_tuple_that_holds_it_and_nothing_more() -> None:
    # What the two record readings below are stated in, measured rather than
    # assumed. Every claim about a Value Object record's price rests on a row
    # costing its own tuple and one pointer per position, so the price is derived
    # from the interpreter's own sizing and this is what holds the interpreter to
    # it: the marginal cost of one more row, in a structure that names it, is the
    # row plus the position naming it. An interpreter that ever charged a row
    # differently would fail here rather than silently moving what a record step
    # means. Zero positions is read first and is not one more of the same
    # reading: it is what a Many occurrence's zero-element value is, and it costs
    # the naming position alone, because the interpreter answers every empty
    # tuple with one shared object. That is the fact every zero-state price below
    # rests on.
    tracemalloc.start()
    try:
        for positions in (0, *_LEAVES):
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


def test_a_top_level_one_occurrence_costs_one_position_in_the_row_and_its_own_record() -> None:
    # And the population the other document steps hold still, for the first of the
    # two branches a reduction has: one more top-level ONE Value Object on the
    # measured Entity, at the same members, leaves, and elements. A One occurrence
    # is a position in the member row after the Attributes, holding the one record
    # it reduced to — so it costs a pointer and a row, and the wrapper the replaced
    # representation put around each one costs nothing here because there is no
    # wrapper. Read at two graph sizes for the reason the member step is.
    small = _member_rows(_CELLS) * _one_occurrence_bytes(_LEAVES[0])
    large = _member_rows(_LARGER) * _one_occurrence_bytes(_LEAVES[0])
    assert _step(_seam, _WIDER_ONES, _CELLS) == small
    assert _step(_seam, _WIDER_ONES, _LARGER) == large


def test_a_top_level_many_occurrence_costs_its_row_of_elements_and_a_record_for_each() -> None:
    # The other branch, and a reading with no substitute anywhere else in this
    # suite: one more top-level MANY Value Object, at the same members, leaves, and
    # elements. `_structure_occurrence` reduces a Many through its own branch, so a
    # carrier that came back around Many occurrences alone would be a constant per
    # projection — invisible to the crossed grid, which never varies a document;
    # invisible to the leaf and element steps, which move populations underneath a
    # fixed set of occurrences; and invisible to the One step above, which adds an
    # occurrence the Many branch never sees. What it may cost is the position in
    # the member row, the row of element positions, and one narrow record per
    # element. Read at two graph sizes for the reason the member step is.
    small = _member_rows(_CELLS) * _many_occurrence_bytes(_ELEMENTS[0])
    large = _member_rows(_LARGER) * _many_occurrence_bytes(_ELEMENTS[0])
    assert _step(_seam, _WIDER_MANYS, _CELLS) == small
    assert _step(_seam, _WIDER_MANYS, _LARGER) == large


def test_a_whole_document_costs_the_rows_its_declaration_names_and_nothing_at_any_depth() -> None:
    # What the four steps cannot say between them, and the reading that needs no
    # fifth axis to say it: what a graph retains ABOVE the same graph declaring no
    # Value Object at all, against the price of the whole declared tree — every
    # occurrence, every record, every position, at every depth. A step prices the
    # population it MOVES and absorbs every population it holds still, so a cost
    # charged once per NESTED occurrence is a constant per projection that the
    # crossed grid, both record steps, and both top-level occurrence steps
    # arithmetically cannot see: nothing here varies how many occurrences a
    # document nests. This baseline holds none of them, so the difference is the
    # whole subtree and the price is a recursion over the declaration rather than
    # a term per level anyone enumerated. Read at every point that declares a
    # document and at two graph sizes, so a cost fixed per model has nowhere to
    # sit either.
    for point in _DOCUMENTS:
        assert _step(_seam, point, _CELLS, _BARE) == _document_bytes(point, _CELLS), point
        assert _step(_seam, point, _LARGER, _BARE) == _document_bytes(point, _LARGER), point


def test_a_whole_document_costs_that_same_total_in_every_state_its_positions_admit() -> None:
    # The other half of the total, and the one an exact total over fully carried
    # documents cannot state. Every reading above is taken over a document whose
    # every One is supplied and whose every Many holds elements, so a carrier that
    # came back on a ZERO-state branch — a Many loaded empty, a One stored null or
    # omitted, a member the read never carried — sits on neither side of any
    # difference and leaves all of them exact. This reads the same exact total
    # over the widest declaration in every state its positions admit, against the
    # same document-free baseline, with the price state-aware: a zeroed occurrence
    # costs its position and nothing under it, because `None` and `()` are both
    # objects the interpreter already had. So the equalities say what a state
    # COSTS as well as that it is reached — including that zeroing every leaf, or
    # every Attribute no join reads, moves nothing at all, since a position holds
    # its pointer whatever is at the end of it. One graph size is enough where the
    # four steps need two: this is an exact equality against a price already
    # multiplied by the cells, so a byte charged per row has no size to hide at.
    for point in _STATE_POINTS:
        assert _step(_seam, point, _CELLS, _BARE) == _document_bytes(point, _CELLS), point


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
            builder = GraphBuilder(ViewSchema(_slot_table(_LEAST)))
            root = convert_row(workload.parents[0], parent, builder, source=_ROOT_SOURCE)
            children = tuple(
                convert_row(row, level, builder, source=_BROAD_SOURCE)
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


def _occurrence_wrapping_seam(point: _Point, cells: int, branch: Multiplicity) -> Seam:
    """``point``'s materialization, plus one carrier per top-level occurrence of
    ``branch``'s multiplicity on every projection — the population the pre-cutover
    graph's ``ValueObjectOccurrenceInput`` was, which is fixed per projection and
    therefore invisible to every reading that varies something inside a document.

    Taken one multiplicity at a time because the production reduction is written
    one multiplicity at a time: a wrapper that returned to the Many branch alone
    is a different defect from one that returned to both, and only a control that
    can be that narrow shows which reading catches it.
    """

    def run(sample: Callable[[], None]) -> None:
        graph, merge = _compose(point, cells)
        rows = graph_rows(graph)
        carriers = [
            _CellCarrier(row[position])
            for layout, row in zip(rows.layouts, rows.member_rows, strict=True)
            for position, declared in enumerate(layout.occurrences, start=layout.attribute_count)
            if declared.multiplicity is branch
        ]
        sample()
        assert graph is not None and merge is not None and carriers is not None

    return run


def _one_occurrence_wrapping_seam(point: _Point, cells: int = _CELLS) -> Seam:
    """The control wrapping every top-level ONE occurrence and nothing else."""
    return _occurrence_wrapping_seam(point, cells, Multiplicity.ONE)


def _many_occurrence_wrapping_seam(point: _Point, cells: int = _CELLS) -> Seam:
    """The control wrapping every top-level MANY occurrence and nothing else."""
    return _occurrence_wrapping_seam(point, cells, Multiplicity.MANY)


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


def test_the_one_occurrence_step_is_what_refuses_a_wrapper_around_a_one_occurrence() -> None:
    # And what the two occurrence readings are worth, starting with the One
    # branch. A carrier held once per top-level One occurrence is a constant per
    # projection, so it stands still down every axis the grid varies and is
    # absorbed whole by the fit's origin at each graph size. It moves the One step
    # by an object per One occurrence, and the Many step not at all — which is the
    # half that says the two steps read two populations rather than one twice.
    step = _step(_one_occurrence_wrapping_seam, _WIDER_ONES, _CELLS)
    assert step > _member_rows(_CELLS) * _one_occurrence_bytes(_LEAVES[0])
    with pytest.raises(AssertionError):
        assert step == _member_rows(_CELLS) * _one_occurrence_bytes(_LEAVES[0])
    assert _step(_one_occurrence_wrapping_seam, _WIDER_MANYS, _CELLS) == _member_rows(
        _CELLS
    ) * _many_occurrence_bytes(_ELEMENTS[0])


def test_the_many_occurrence_step_is_what_refuses_a_wrapper_around_a_many_occurrence() -> None:
    # And the Many branch, which is the reading with no substitute anywhere: a
    # carrier around the Many occurrences alone is what a regression confined to
    # `_structure_occurrence`'s Many branch leaves behind, and it is a fixed count
    # per projection that the crossed grid, both record readings, and the One step
    # above all hold still. It moves this step by an object per Many occurrence,
    # and the One step not at all — so the One step alone would have passed a
    # graph carrying it.
    step = _step(_many_occurrence_wrapping_seam, _WIDER_MANYS, _CELLS)
    assert step > _member_rows(_CELLS) * _many_occurrence_bytes(_ELEMENTS[0])
    with pytest.raises(AssertionError):
        assert step == _member_rows(_CELLS) * _many_occurrence_bytes(_ELEMENTS[0])
    assert _step(_many_occurrence_wrapping_seam, _WIDER_ONES, _CELLS) == _member_rows(
        _CELLS
    ) * _one_occurrence_bytes(_LEAVES[0])


def _nested_occurrence_wrapping_seam(point: _Point, cells: int = _CELLS) -> Seam:
    """``point``'s materialization, plus one carrier per occurrence NESTED inside
    another one that no axis in this suite counts.

    The population is named by the property that hides it rather than by a depth:
    an occurrence reached from a member row without descending a Many is declared
    once per projection, however wide the members, the leaves, the elements, or
    the top-level occurrence counts grow. Descending a Many would reach
    occurrences the element axis multiplies, and an axis that multiplies a
    population is an axis that prices it — so those are left out, and what is left
    is exactly what every step here holds still.
    """

    def run(sample: Callable[[], None]) -> None:
        graph, merge = _compose(point, cells)
        rows = graph_rows(graph)
        carriers = [
            carrier
            for layout, row in zip(rows.layouts, rows.member_rows, strict=True)
            for position, declared in enumerate(layout.occurrences, start=layout.attribute_count)
            for carrier in _nested_occurrences(row[position], declared)
        ]
        sample()
        assert graph is not None and merge is not None and carriers is not None

    return run


def _nested_occurrences(
    value: object, declared: ValueObjectMetadata | NestedValueObjectMetadata
) -> list[_CellCarrier]:
    """One carrier per occurrence nested under ``value``, and per occurrence
    nested under each of those, stopping at a Many rather than descending its
    elements."""
    if declared.multiplicity is Multiplicity.MANY:
        return []
    positions = cast("tuple[object, ...]", value)
    return [
        carrier
        for offset, nested in enumerate(declared.value_objects, start=len(declared.attributes))
        for carrier in (
            _CellCarrier(positions[offset]),
            *_nested_occurrences(positions[offset], nested),
        )
    ]


def test_the_whole_document_reading_is_what_refuses_a_wrapper_around_a_nested_occurrence() -> None:
    # What that total is worth, against the defect no step in this suite can
    # catch. A carrier held once per nested occurrence is a constant per
    # projection: the crossed grid never varies a document at all, the leaf and
    # element steps move populations underneath a fixed set of occurrences, and
    # each top-level occurrence step adds an occurrence that nests none — so all
    # four steps read exactly their priced values under this control, which is the
    # half that says the total reads a population none of them reaches. The total
    # sees it because the graph it is measured against declares no occurrence for
    # anything to nest inside.
    measured = _step(_nested_occurrence_wrapping_seam, _LEAST, _CELLS, _BARE)
    assert measured > _document_bytes(_LEAST, _CELLS)
    with pytest.raises(AssertionError):
        assert measured == _document_bytes(_LEAST, _CELLS)
    assert (
        _step(_nested_occurrence_wrapping_seam, _WIDER_LEAVES, _CELLS)
        == _leaf_records(_CELLS) * _POINTER
    )
    assert _step(_nested_occurrence_wrapping_seam, _WIDER_ELEMENTS, _CELLS) == _member_rows(
        _CELLS
    ) * _element_bytes(_LEAVES[0])
    assert _step(_nested_occurrence_wrapping_seam, _WIDER_ONES, _CELLS) == _member_rows(
        _CELLS
    ) * _one_occurrence_bytes(_LEAVES[0])
    assert _step(_nested_occurrence_wrapping_seam, _WIDER_MANYS, _CELLS) == _member_rows(
        _CELLS
    ) * _many_occurrence_bytes(_ELEMENTS[0])


def _zero_state_wrapping_seam(point: _Point, cells: int = _CELLS) -> Seam:
    """``point``'s materialization, plus one carrier per member position holding
    a ZERO value — an Attribute or leaf reading ``ABSENT`` or ``None``, a One
    occurrence reading either, a Many occurrence reading ``ABSENT`` or the empty
    tuple — at every depth.

    The population a fully carried document has none of, which is what makes this
    control invisible to every reading taken over one: the crossed grid, the four
    document steps, and the carried total all convert rows whose every declared
    member is supplied, so this seam holds nothing at all at any of their points.

    Selected out of :func:`_positions` rather than walked again, so the population
    it wraps is the same one the census asserts a closed set of states over — the
    control cannot come to cover less than the proof claims it covers.
    """

    def run(sample: Callable[[], None]) -> None:
        graph, merge = _compose(point, cells)
        rows = graph_rows(graph)
        carriers = [
            _CellCarrier(position.value)
            for layout, row in zip(rows.layouts, rows.member_rows, strict=True)
            for position in _positions(layout, row)
            if position.state != "carried"
        ]
        sample()
        assert graph is not None and merge is not None and carriers is not None

    return run


def test_the_state_readings_are_what_refuse_a_wrapper_around_a_position_stored_zero() -> None:
    # What the state sweep is worth, against the defect every reading over a
    # carried document is blind to by construction. A carrier held once per
    # position in a zero state is retained on exactly the branches a fully
    # supplied row never takes, so this control holds nothing at all at any point
    # that declares a carried document: the total is exact at every one of them,
    # and therefore so is each of the four steps between two of them. That is the
    # half saying the state readings reach a population no other reading here
    # does. Every state but the carried one fails, by one carrier per position it
    # zeroed — so the sweep catches a wrapper on any single branch, whichever
    # population and whichever nesting rank it came back on.
    for point in _DOCUMENTS:
        assert _step(_zero_state_wrapping_seam, point, _CELLS, _BARE) == _document_bytes(
            point, _CELLS
        ), point
    for point in _STATE_POINTS:
        measured = _step(_zero_state_wrapping_seam, point, _CELLS, _BARE)
        priced = _document_bytes(point, _CELLS)
        if point.stored == _CARRIED and point.projected:
            assert measured == priced, point
            continue
        assert measured > priced, point
        with pytest.raises(AssertionError):
            assert measured == priced
