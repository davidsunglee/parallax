"""The canonical scenarios published-instance state is measured over, and the
three arms every reading takes over them.

Six scenarios — shallow, wide, nested, nullable, partial, polymorphic — carry
retained bytes on both sides of a representation change, and
:data:`WARMED_AUXILIARY` carries the seventh the measurement contract reports
beside them and excludes from every aggregate.

**Three arms, and the two different comparisons they make.**

- :data:`COMPACT` is the "after": the shipping publication path in full, which
  needs no fixture because it is production.
- :data:`LEGACY` is the "before" the aggregates divide, and it is a fixture
  because it has to be — once publication attaches a compact tuple there is no
  legacy path left to measure, so a comparison taken later would have nothing to
  compare against. It was compared against the real path every time it was
  measured, up to and including the reading taken immediately before the flip;
  the flip deleted the path, and with it the comparison.
- :data:`ORDINARY` is neither: it is what any caller gets from the validating
  constructor. It enters no aggregate. It exists because ``spec/python.md`` §2
  states what a published instance retains against an ORDINARY one, which is a
  different comparison from the representation change the aggregates measure,
  and a claim nothing measured until this arm did.

**Every arm is measured on one tree, which is what makes their differences the
representation's.** Every framework slot a declared class carries is carried by
all three — an ordinary value holds the compact and auxiliary pointers exactly
as a published one does, and an Entity of any backing holds the lifecycle slot —
so an aggregate over two of them divides two readings taken over one object
layout, as ``docs/instance-state-baseline.md``'s accounting rule requires.

**Why the legacy fixture is not the ordinary arm.** A materialized node WAS
``cls.model_construct()`` with no arguments followed by one
``object.__setattr__`` per member, which leaves ``__pydantic_fields_set__``
permanently empty — the sharpest part of what publication retained then, and the
part ordinary construction does not reproduce, since a validating constructor
records every member it was passed. A Value Object was different and is
reproduced differently: ``vo_class.model_construct(present, **values)``, where
``present`` is exactly the members the row carried.

**Why each arm also builds a graph of ``count`` nodes.** Construction is the one
timing whose per-call scope differs between the arms: a compact node arrives from
an ``EntityGraphConstruction.construct`` call that also pays a scope, a writer,
root validation and factory buffering, where the other two arms build a node and
nothing else. Timing a one-node build against an eleven-node one separates the
two, so what the report prints as construction is the cost of one MORE node under
each arm — the quantity the arms hold in common — with the per-call remainder
printed beside it.

**Why the compact arm also reports what its own callbacks cost.** That split
cancels a call's FIXED cost and not its per-NODE one, and a ``construct`` call
does per-node work outside the callbacks its caller supplies. The pre-flip path
paid exactly that work through the same call; the legacy fixture reproduces the
node BUILDING alone and pays none of it, so the two arms' ``node µs`` are still
not the same scope. :func:`compact_callback_ns` measures the difference by timing
one call's own callbacks from inside them, which lets the report state a
like-for-like construction ratio it derives rather than a correction in prose.
Only the compact arm carries one: an arm whose call IS a loop over its node
builder has nothing outside that builder to separate.

**What a scenario carries.** One positional member row, ``ABSENT``-spelled and
aligned to the exact Entity's ``EntityLayout`` — the same row a compiled read
lays out and hands across ``populate``'s door, with nested tuples at every Value
Object containment depth. Every leaf value is built once at import, outside every
measurement window, so a reading counts the positions a node holds and not the
payload it borrows.

Exported names carry no leading underscore: importing an underscored name across
modules is a `reportPrivateUsage` error under pyright strict, so privacy is
carried by this MODULE's underscore. Read by ``test_instance_state_baseline.py``,
by ``tools/instance_state_overhead.py`` and by the script one child runs,
``tools/instance_state_reading.py``; never imported by production code.

This module deliberately avoids ``from __future__ import annotations`` so the
declaration engine reads the live ``Attr[T]`` / ``Rel[T]`` objects directly, as
``tests/_support/snapshot_models.py`` does for the same reason.
"""

from collections.abc import Callable
from dataclasses import dataclass
from decimal import Decimal
from functools import cached_property
from time import perf_counter
from typing import Any, Final, cast

from pydantic import BaseModel, PrivateAttr

from parallax.core import (
    MANY_TO_ONE,
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
from parallax.core.entity import (
    UNLOADED,
)
from parallax.core.entity._construction_input import ABSENT, NodeHandle
from parallax.core.entity._declaration import shape_of
from parallax.core.entity._entity import attach_lifecycle_state, wire_names_of
from parallax.core.entity._graph_construction import EntityGraphWriter, graph_construction_of
from parallax.core.entity._instance_state import COMPACT_STATE_SLOT
from parallax.core.entity._layout import EntityLayout
from parallax.core.entity._model import DomainModel as ModelType
from parallax.core.entity._model import cataloged_model, class_index
from parallax.core.entity._pydantic_storage import attach_instance_state, instance_state
from parallax.core.metamodel import (
    EntityIdentity,
    Multiplicity,
    NestedValueObjectMetadata,
    ValueObjectMetadata,
)
from parallax.snapshot._inspection import SnapshotNodeState

__all__ = [
    "ARMS",
    "COMPACT",
    "LEGACY",
    "ORDINARY",
    "REPORTED",
    "SCENARIOS",
    "WARMED_AUXILIARY",
    "Arm",
    "LegacyPlan",
    "Scenario",
    "compact_callback_ns",
    "scenario_named",
    "state_cells",
]

NAMESPACE: Final = "instance.state"

_VoContainer = ValueObjectMetadata | NestedValueObjectMetadata


# --------------------------------------------------------------------------- #
# The scenario models. Bespoke, because the canonical mix is stated as widths   #
# and presence states rather than as a domain: the corpus carries no eight-     #
# optional-member Entity read twice at two presence states, which is the whole  #
# distinction the nullable and partial scenarios exist to separate.             #
#                                                                              #
# Every root declares one self-referential broad relationship, left unloaded.   #
# Publication writes EVERY declared relationship slot on every node, so a mix   #
# declaring none would understate the publication arms; one per scenario keeps  #
# that cost uniform across the mix and attributable to a single position. The   #
# ordinary arm writes none, because ordinary construction does not.             #
# --------------------------------------------------------------------------- #


class Shallow(Entity, table="instance_state_shallow", namespace=NAMESPACE):
    """Four Attributes, one relationship: the small-object end of the mix."""

    id: Attr[int] = attr(primary_key=True)
    parent_id: Attr[int | None]
    name: Attr[str | None] = attr(max_length=32)
    amount: Attr[Decimal | None] = attr(precision=18, scale=2)
    parent: Rel["Shallow | None"] = rel(cardinality=MANY_TO_ONE, join=("parent_id", "id"))


class Wide(Entity, table="instance_state_wide", namespace=NAMESPACE):
    """Sixteen Attributes across four Neutral Types, every one carried."""

    id: Attr[int] = attr(primary_key=True)
    parent_id: Attr[int | None]
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
    parent: Rel["Wide | None"] = rel(cardinality=MANY_TO_ONE, join=("parent_id", "id"))


class Geo(ValueObject):
    """The nested leaf of the nested scenario's One occurrence."""

    latitude: Attr[float | None]
    longitude: Attr[float | None]


class Address(ValueObject):
    """A One occurrence carrying leaves and a nested One of its own."""

    line1: Attr[str | None]
    city: Attr[str | None]
    geo: Attr[Geo | None]


class Phone(ValueObject):
    """The element of the nested scenario's Many occurrence."""

    kind: Attr[str | None]
    number: Attr[str | None]


class Nested(Entity, table="instance_state_nested", namespace=NAMESPACE):
    """The directional nested shape: an Address carrying a Geo, and two Phone
    records under a Many occurrence."""

    id: Attr[int] = attr(primary_key=True)
    parent_id: Attr[int | None]
    code: Attr[str | None] = attr(max_length=16)
    address: Attr[Address | None]
    phones: Attr[tuple[Phone, ...]]
    parent: Rel["Nested | None"] = rel(cardinality=MANY_TO_ONE, join=("parent_id", "id"))


class Optionals(Entity, table="instance_state_optionals", namespace=NAMESPACE):
    """Eight optional Attributes beside the key and the join column.

    Two scenarios read the same class, which is what isolates presence as the
    only variable between them: `nullable` carries every position as an explicit
    null, `partial` carries three and omits five.
    """

    id: Attr[int] = attr(primary_key=True)
    parent_id: Attr[int | None]
    o01: Attr[str | None] = attr(max_length=32)
    o02: Attr[str | None] = attr(max_length=32)
    o03: Attr[int | None] = attr(type=Int32)
    o04: Attr[int | None] = attr(type=Int32)
    o05: Attr[float | None]
    o06: Attr[bool | None]
    o07: Attr[Decimal | None] = attr(precision=18, scale=2)
    o08: Attr[str | None] = attr(max_length=32)
    parent: Rel["Optionals | None"] = rel(cardinality=MANY_TO_ONE, join=("parent_id", "id"))


class Vehicle(
    Entity,
    table="instance_state_vehicle",
    namespace=NAMESPACE,
    inheritance=AbstractRoot(TablePerHierarchy(tag_column="kind")),
):
    """The polymorphic family's root, contributing the inherited prefix."""

    id: Attr[int] = attr(primary_key=True)
    parent_id: Attr[int | None]
    label: Attr[str | None] = attr(max_length=32)
    weight: Attr[float | None]
    parent: Rel["Vehicle | None"] = rel(cardinality=MANY_TO_ONE, join=("parent_id", "id"))


class Wheeled(Vehicle, namespace=NAMESPACE, inheritance=AbstractSubtype):
    """The abstract middle, so the published concrete's ordinals sit behind two
    contributors rather than one."""

    axles: Attr[int | None] = attr(type=Int32)


class Car(Wheeled, namespace=NAMESPACE, inheritance=ConcreteSubtype(tag_value="car")):
    """The published concrete."""

    doors: Attr[int | None] = attr(type=Int32)
    electric: Attr[bool | None]


class Warmed(Entity, table="instance_state_warmed", namespace=NAMESPACE):
    """The same four Attributes as `shallow`, plus the two kinds of author-owned
    state that live outside a published row.

    Reported beside the canonical mix and excluded from both aggregates: a
    ``PrivateAttr``'s value and a ``cached_property``'s result are state the
    author asked for, so charging a representation change with them would credit
    or debit it for something neither backing decides.
    """

    id: Attr[int] = attr(primary_key=True)
    parent_id: Attr[int | None]
    name: Attr[str | None] = attr(max_length=32)
    amount: Attr[Decimal | None] = attr(precision=18, scale=2)
    parent: Rel["Warmed | None"] = rel(cardinality=MANY_TO_ONE, join=("parent_id", "id"))

    _revision = PrivateAttr(default=0)

    @cached_property
    def label(self) -> str:
        """Warmed inside every window, so the memoized result is counted."""
        return f"{self.name}/{self.id}"


SHALLOW_MODEL: Final = DomainModel(Shallow)
WIDE_MODEL: Final = DomainModel(Wide)
NESTED_MODEL: Final = DomainModel(Nested)
OPTIONALS_MODEL: Final = DomainModel(Optionals)
VEHICLE_MODEL: Final = DomainModel(Vehicle, Wheeled, Car)
WARMED_MODEL: Final = DomainModel(Warmed)


# --------------------------------------------------------------------------- #
# The payloads, built at IMPORT time — which is what excludes decoded payload   #
# leaves from every window a reading opens.                                    #
# --------------------------------------------------------------------------- #

_SHALLOW_ROW: Final[tuple[object, ...]] = (7, None, "shallow-name", Decimal("12.50"))

_WIDE_ROW: Final[tuple[object, ...]] = (
    7,
    None,
    *(f"wide-value-{index:02d}" for index in range(1, 9)),
    *(100 + index for index in range(1, 5)),
    1.5,
    2.5,
)

_GEO_ROW: Final[tuple[object, ...]] = (51.5074, -0.1278)
_ADDRESS_ROW: Final[tuple[object, ...]] = ("221B Baker Street", "London", _GEO_ROW)
_PHONE_ROWS: Final[tuple[object, ...]] = (
    ("mobile", "+44 20 7946 0958"),
    ("work", "+44 20 7946 1000"),
)
_NESTED_ROW: Final[tuple[object, ...]] = (7, None, "NST", _ADDRESS_ROW, _PHONE_ROWS)

_NULLABLE_ROW: Final[tuple[object, ...]] = (7, None, None, None, None, None, None, None, None, None)
_PARTIAL_ROW: Final[tuple[object, ...]] = (
    7,
    ABSENT,
    "carried",
    ABSENT,
    3,
    ABSENT,
    ABSENT,
    ABSENT,
    ABSENT,
    ABSENT,
)

_CAR_ROW: Final[tuple[object, ...]] = (7, None, "estate", 1420.0, 2, 5, False)

_WARMED_ROW: Final[tuple[object, ...]] = (7, None, "warmed-name", Decimal("12.50"))


# --------------------------------------------------------------------------- #
# The three arms.                                                              #
# --------------------------------------------------------------------------- #


@dataclass(frozen=True, slots=True)
class LegacyPlan:
    """Everything the legacy arm resolves once per exact Entity rather than per node.

    Entity Graph Construction memoizes exactly this much — the concrete class and
    the identity-to-Python-name maps — on its ``facts_for`` cache, so a fixture
    that re-derived it per node would price a derivation publication does not
    make and would swamp the per-node cost the reading is taken for.
    """

    cls: type
    attributes: tuple[tuple[int, str], ...]
    """Each carried-or-not Attribute as its row position and Python name."""
    occurrences: tuple[tuple[int, str, _VoContainer, type], ...]
    """Each top-level occurrence as its row position, Python name, declared
    metadata, and Value Object class."""
    relationships: tuple[str, ...]
    """Every declared relationship's Python name, in declaration order."""


@dataclass(frozen=True)
class Scenario:
    """One canonical shape and the input row its arms are built from."""

    name: str
    summary: str
    model: ModelType
    entity: EntityIdentity
    values: tuple[object, ...]
    warms: bool = False
    """Whether every arm reads this scenario's ``cached_property`` before the
    sample, so the memoized result is state the reading counts."""

    @cached_property
    def layout(self) -> EntityLayout:
        """The exact Entity's member layout — the order ``values`` is read in."""
        return cataloged_model(self.model).layouts.entity(self.entity)

    @cached_property
    def unloaded(self) -> tuple[object, ...]:
        """One unloaded position per navigable relationship, which is the
        relationship row publication takes.

        Derived from the layout rather than spelled per scenario. Every position
        holds the same sentinel, so a literal row would pin no value — only a
        width, which is the layout's own and which spelling out again would leave
        one more thing to keep in step for a reading that grades nothing.
        """
        return (UNLOADED,) * len(self.layout.relationships)

    @cached_property
    def plan(self) -> LegacyPlan:
        """What the legacy arm resolves once, derived on first reach."""
        classes = class_index(self.model)
        assert classes is not None, "a class-backed Domain Model indexes its classes"
        cls = classes.class_of(self.entity)
        assert cls is not None, self.entity
        names = wire_names_of(cls)
        return LegacyPlan(
            cls=cls,
            attributes=tuple(
                (position, names.name_to_py[attribute.identity.name])
                for position, attribute in enumerate(self.layout.attributes)
            ),
            occurrences=tuple(
                (
                    position,
                    names.name_to_py[occurrence.identity.path[-1]],
                    occurrence,
                    names.vo_classes[names.name_to_py[occurrence.identity.path[-1]]],
                )
                for position, occurrence in enumerate(
                    self.layout.occurrences, start=self.layout.attribute_count
                )
            ),
            relationships=tuple(names.relationship_py.values()),
        )

    @property
    def cls(self) -> type:
        """The exact concrete class this scenario publishes."""
        return self.plan.cls

    def state(self) -> SnapshotNodeState:
        """One node's lifecycle state, allocated fresh.

        The real `SnapshotNodeState` rather than a stand-in, because the primary
        aggregate counts lifecycle state and a stand-in would misreport the half
        of it that does not change. Allocated per call rather than shared: a state
        object built outside the window would be borrowed by every arm and priced
        by none.
        """
        return SnapshotNodeState(entity=self.entity, views={})


def legacy_publication(scenario: Scenario, state: object | None) -> object:
    """``scenario``'s node built the way publication built one before the flip.

    Zero-argument ``model_construct`` and one ``object.__setattr__`` per member,
    so the empty fields-set a materialized node carried then is reproduced rather
    than approximated; every declared relationship slot written, since
    publication installed the unloaded sentinel where a read loaded nothing; and
    the lifecycle state written last, as the construction call's own final phase
    still does. That write reaches the ``Entity`` root's real slot today and
    reached the node's storage while this fixture stood for the shipping path —
    the difference the frozen and current layout rows in
    ``docs/instance-state-baseline.md`` account for.
    """
    plan = scenario.plan
    values = scenario.values
    instance = cast("Any", plan.cls).model_construct()
    for position, py_name in plan.attributes:
        value = values[position]
        if value is not ABSENT:
            object.__setattr__(instance, py_name, value)
    for position, py_name, occurrence, vo_class in plan.occurrences:
        value = values[position]
        if value is not ABSENT:
            object.__setattr__(instance, py_name, _legacy_occurrence(value, occurrence, vo_class))
    for py_name in plan.relationships:
        attach_instance_state(instance, py_name, UNLOADED)
    if state is not None:
        attach_lifecycle_state(instance, state)
    return _warmed(scenario, instance)


def compact_publication(scenario: Scenario, state: object | None) -> object:
    """``scenario``'s node built the way publication builds one today.

    The shipping path in full rather than a fixture of it: one Entity Graph
    Construction call allocating one shell, populating it with the scenario's
    positional member row and one unloaded position per navigable relationship,
    and attaching one complete row exactly once. There is nothing here to keep in
    step with production, because it IS production — which is the half of the
    comparison the legacy arm cannot be.
    """
    construction = graph_construction_of(scenario.model)
    entity = scenario.entity
    members = scenario.values
    relationships = scenario.unloaded

    def build(writer: EntityGraphWriter) -> tuple[NodeHandle, ...]:
        handle = writer.allocate(entity)
        writer.populate(handle, members, relationships)
        return (handle,)

    roots = construction.construct(
        build,
        state_factory=None if state is None else lambda _view, _handle: state,
    )
    return _warmed(scenario, roots[0])


def ordinary_publication(scenario: Scenario, state: object | None) -> object:
    """``scenario``'s node built the way any caller builds one.

    The validating constructor, with the members the row carried passed by
    keyword and the absent ones left to their declared defaults — so an ordinary
    node records exactly the presence a caller stated, where the legacy fixture
    recorded none and a published node records what its row carried. Its
    occurrences are ordinary Value Objects for the same reason.

    It is not publication and stands for none: it is the comparand
    ``spec/python.md`` §2's Interface statement is made against, which is a
    different question from the before-and-after the aggregates divide.

    It carries no lifecycle state and refuses one, because ``spec/python.md`` §3
    says a plainly constructed instance has none to carry. Attaching one anyway
    would put 136 bytes into the denominator of the §2 figure that no caller's
    instance holds, which flatters the published side by about four points.
    """
    if state is not None:
        raise ValueError(
            "an ordinary instance has no lifecycle state to carry (spec/python.md §3), "
            "so the ordinary arm may not be given one"
        )
    plan = scenario.plan
    values = scenario.values
    members: dict[str, object] = {}
    for position, py_name in plan.attributes:
        value = values[position]
        if value is not ABSENT:
            members[py_name] = value
    for position, py_name, occurrence, vo_class in plan.occurrences:
        value = values[position]
        if value is not ABSENT:
            members[py_name] = _ordinary_occurrence(value, occurrence, vo_class)
    return _warmed(scenario, cast("Any", plan.cls)(**members))


def _ordinary_occurrence(value: object, declared: _VoContainer, vo_class: type) -> object:
    """One occurrence slot as a caller would pass it, the declared multiplicity
    deciding the shape."""
    if declared.multiplicity is Multiplicity.MANY:
        rows = cast("tuple[object, ...]", value) if isinstance(value, tuple) else ()
        return tuple(
            _ordinary_record(cast("tuple[object, ...]", row), declared, vo_class) for row in rows
        )
    if value is None:
        return None
    return _ordinary_record(cast("tuple[object, ...]", value), declared, vo_class)


def _ordinary_record(row: tuple[object, ...], declared: _VoContainer, vo_class: type) -> object:
    """One positional Value Object row as an ordinary instance, at every depth.

    An omitted leaf is omitted rather than passed as ``None``, which is what
    keeps it outside ``model_fields_set`` while a leaf carried as ``None`` is
    inside it — the same distinction the legacy fixture spells with an explicit
    present set.
    """
    shape = shape_of(vo_class)
    values: dict[str, object] = {}
    for position, leaf in enumerate(declared.attributes):
        value = row[position]
        if value is not ABSENT:
            values[shape.name_to_py[leaf.identity.name]] = value
    for position, nested in enumerate(declared.value_objects, start=len(declared.attributes)):
        value = row[position]
        if value is ABSENT:
            continue
        py_name = shape.name_to_py[nested.identity.path[-1]]
        values[py_name] = _ordinary_occurrence(value, nested, shape.nested_classes[py_name])
    return cast("Any", vo_class)(**values)


def _one_at_a_time(
    node: Callable[[Scenario, object | None], object],
    *,
    lifecycle: bool,
) -> Callable[[Scenario, int], tuple[object, ...]]:
    """``count`` nodes from an arm that builds one node per call.

    Both non-compact arms build a node and nothing else, so their graph IS the
    loop — which is what makes their per-call remainder measure as the zero it
    should be, rather than as an allowance the comparison would have to grant
    them. ``lifecycle`` says whether that arm's node carries state at all, which
    is a fact about the arm rather than about the reading: a published node has
    state under either backing and an ordinary one has none.
    """

    def graph(scenario: Scenario, count: int) -> tuple[object, ...]:
        return tuple(node(scenario, scenario.state() if lifecycle else None) for _ in range(count))

    return graph


def compact_graph(scenario: Scenario, count: int) -> tuple[object, ...]:
    """``count`` of ``scenario``'s nodes from ONE Entity Graph Construction call.

    Allocation before any populate, as the writer requires, and one lifecycle
    state per node, so the only thing that varies with ``count`` is how many
    nodes one call's scaffolding is spread over.
    """
    construction = graph_construction_of(scenario.model)
    entity = scenario.entity
    members = scenario.values
    relationships = scenario.unloaded

    def build(writer: EntityGraphWriter) -> tuple[NodeHandle, ...]:
        handles = tuple(writer.allocate(entity) for _ in range(count))
        for handle in handles:
            writer.populate(handle, members, relationships)
        return handles

    roots = construction.construct(build, state_factory=lambda _view, _handle: scenario.state())
    return tuple(_warmed(scenario, root) for root in roots)


def compact_callback_ns(scenario: Scenario, count: int) -> float:
    """Nanoseconds one :func:`compact_graph` call spends inside its OWN work.

    The same call, built the same way, with the arm's two callbacks and its
    warming loop timed from inside them: the build callback, which is the node
    building the legacy fixture reproduces; each state-factory invocation, which
    is the lifecycle state the fixture also creates; and the warming loop, which
    is author-owned state both arms pay per node. What is left outside is the
    per-node work ``construct`` itself does — the populated check, root
    validation, the resolution view each factory invocation gets, the buffered
    attach, and the root tuple — which is what the pre-flip path paid through the
    same call and the fixture does not reproduce.

    A SEPARATE call from the one :func:`compact_graph` answers, so no timer runs
    inside the call the report's own construction figure is taken over: reading
    the clock twelve times inside an eleven-node build would move the number this
    correction is applied to.

    The lifecycle ATTACH stays outside — it is one slot write per node inside
    ``construct``'s own loop, and the fixture pays one too — so the residue this
    leaves is generous to the compact arm by that much.
    """
    construction = graph_construction_of(scenario.model)
    entity = scenario.entity
    members = scenario.values
    relationships = scenario.unloaded
    inside = 0.0

    def build(writer: EntityGraphWriter) -> tuple[NodeHandle, ...]:
        nonlocal inside
        start = perf_counter()
        handles = tuple(writer.allocate(entity) for _ in range(count))
        for handle in handles:
            writer.populate(handle, members, relationships)
        inside += perf_counter() - start
        return handles

    def state_factory(_view: object, _handle: NodeHandle) -> object:
        nonlocal inside
        start = perf_counter()
        state = scenario.state()
        inside += perf_counter() - start
        return state

    roots = construction.construct(build, state_factory=state_factory)
    start = perf_counter()
    for root in roots:
        _warmed(scenario, root)
    inside += perf_counter() - start
    return inside * 1e9


@dataclass(frozen=True, slots=True)
class Arm:
    """One way of building ``scenario``'s node, at both scopes a reading needs.

    The two builders are paired here rather than at the reading, so a graph
    builder cannot be measured against another arm's node builder — which would
    silently make the construction figure a difference between two arms rather
    than a cost of one.
    """

    name: str
    node: Callable[[Scenario, object | None], object]
    """One node, held at the sample: what the byte readings are taken over."""
    graph: Callable[[Scenario, int], tuple[object, ...]]
    """``count`` nodes, so the cost of one more is separable from the call's."""
    lifecycle: bool
    """Whether a node of this arm carries lifecycle state at all.

    A published node does under either backing, so the reading takes it twice —
    once carrying state and once without — and the pair is what the primary and
    secondary aggregates divide. An ordinary node never does
    (`spec/python.md` §3), so the reading must not attach one: an arm asked for
    a comparand a caller cannot hold answers about no instance that exists.
    """
    callbacks_ns: Callable[[Scenario, int], float] | None = None
    """Nanoseconds one call of this arm spends inside its own callbacks, or
    ``None`` for an arm whose call IS its node builder.

    ``None`` is the honest answer for the two fixture arms rather than a missing
    measurement: their graph is a loop over the node builder, so there is nothing
    outside that builder for a call to spend time in and nothing to separate. The
    compact arm's call runs per-node work of its own around the callbacks it is
    given, and this is what measures it."""


ORDINARY: Final = Arm(
    "ordinary",
    ordinary_publication,
    _one_at_a_time(ordinary_publication, lifecycle=False),
    lifecycle=False,
)
LEGACY: Final = Arm(
    "legacy", legacy_publication, _one_at_a_time(legacy_publication, lifecycle=True), lifecycle=True
)
COMPACT: Final = Arm(
    "compact", compact_publication, compact_graph, lifecycle=True, callbacks_ns=compact_callback_ns
)

ARMS: Final[tuple[Arm, ...]] = (ORDINARY, LEGACY, COMPACT)
"""Every arm a reading is taken under, in the order the tables print them."""


def _warmed(scenario: Scenario, instance: object) -> object:
    """``instance``, with its author-owned auxiliary state warmed if the scenario
    asks for it.

    Inside the arm rather than outside it, so the memoized result is allocated
    within whatever window the arm is measured in and is counted as state the
    node holds rather than borrowed from before it.
    """
    if scenario.warms:
        _ = cast("Any", instance).label
    return instance


def state_cells(instance: object) -> int:
    """How many positions ``instance``'s backing holds, asked without creating any.

    A published value answers its row's width — the presence bitmap, every
    declared member, and every declared relationship — and an ordinary one the
    entries its real storage holds. Reading the row off its slot rather than
    through the value's presented mapping is what keeps the question about the
    representation; asking an ordinary value is safe because it has storage
    already, and asking a published one this way never creates any.
    """
    row = object.__getattribute__(instance, COMPACT_STATE_SLOT)
    if row is not None:
        return len(cast("tuple[object, ...]", row))
    return len(instance_state(cast("BaseModel", instance)))


def _legacy_occurrence(value: object, declared: _VoContainer, vo_class: type) -> object:
    """One occurrence slot, the declared multiplicity deciding the shape."""
    if declared.multiplicity is Multiplicity.MANY:
        rows = cast("tuple[object, ...]", value) if isinstance(value, tuple) else ()
        return tuple(
            _legacy_record(cast("tuple[object, ...]", row), declared, vo_class) for row in rows
        )
    if value is None:
        return None
    return _legacy_record(cast("tuple[object, ...]", value), declared, vo_class)


def _legacy_record(row: tuple[object, ...], declared: _VoContainer, vo_class: type) -> object:
    """One positional Value Object row as a frozen instance, at every depth.

    ``present`` is the members the row carried, so an omitted leaf reads as its
    absent default and stays outside ``model_fields_set`` while a leaf carried as
    ``None`` reads the same and is inside it.
    """
    shape = shape_of(vo_class)
    values: dict[str, object] = {}
    present: set[str] = set()
    for position, leaf in enumerate(declared.attributes):
        py_name = shape.name_to_py[leaf.identity.name]
        value = row[position]
        if value is ABSENT:
            values[py_name] = None
            continue
        present.add(py_name)
        values[py_name] = value
    for position, nested in enumerate(declared.value_objects, start=len(declared.attributes)):
        py_name = shape.name_to_py[nested.identity.path[-1]]
        value = row[position]
        if value is ABSENT:
            values[py_name] = () if py_name in shape.many_py else None
            continue
        present.add(py_name)
        values[py_name] = _legacy_occurrence(value, nested, shape.nested_classes[py_name])
    return cast("Any", vo_class).model_construct(present, **values)


# --------------------------------------------------------------------------- #
# The canonical mix.                                                           #
# --------------------------------------------------------------------------- #

SCENARIOS: Final[tuple[Scenario, ...]] = (
    Scenario(
        name="shallow",
        summary="4 Attributes, 1 unloaded relationship",
        model=SHALLOW_MODEL,
        entity=Shallow.identity,
        values=_SHALLOW_ROW,
    ),
    Scenario(
        name="wide",
        summary="16 Attributes, 1 unloaded relationship",
        model=WIDE_MODEL,
        entity=Wide.identity,
        values=_WIDE_ROW,
    ),
    Scenario(
        name="nested",
        summary="3 Attributes, a One occurrence nesting a One, a Many of 2",
        model=NESTED_MODEL,
        entity=Nested.identity,
        values=_NESTED_ROW,
    ),
    Scenario(
        name="nullable",
        summary="10 Attributes, every one carried as an explicit null",
        model=OPTIONALS_MODEL,
        entity=Optionals.identity,
        values=_NULLABLE_ROW,
    ),
    Scenario(
        name="partial",
        summary="the same 10 Attributes, 3 carried and 7 absent",
        model=OPTIONALS_MODEL,
        entity=Optionals.identity,
        values=_PARTIAL_ROW,
    ),
    Scenario(
        name="polymorphic",
        summary="a 3-level family, published as the concrete: 7 Attributes",
        model=VEHICLE_MODEL,
        entity=Car.identity,
        values=_CAR_ROW,
    ),
)


WARMED_AUXILIARY: Final = Scenario(
    name="warmed",
    summary="`shallow`'s 4 Attributes plus a PrivateAttr and a warmed cached_property",
    model=WARMED_MODEL,
    entity=Warmed.identity,
    values=_WARMED_ROW,
    warms=True,
)
"""The scenario the measurement contract requires beside the canonical mix and
outside both aggregates.

Held apart from :data:`SCENARIOS` rather than flagged inside it, so no aggregate
can pick it up by iterating the mix. What it isolates is state neither backing
decides: a ``PrivateAttr``'s value and a ``cached_property``'s result are the
author's, live in ordinary per-instance storage under every backing, and would
credit or debit a representation change with a cost that is not the
representation's.
"""

REPORTED: Final[tuple[Scenario, ...]] = (*SCENARIOS, WARMED_AUXILIARY)
"""Every scenario a reading is taken over — the canonical mix, then the one
excluded from the aggregate."""


def scenario_named(name: str) -> Scenario:
    """The scenario ``name`` names, canonical or reported beside them, or a loud
    rejection."""
    for scenario in REPORTED:
        if scenario.name == name:
            return scenario
    raise KeyError(f"{name!r} is not a measured scenario: {[s.name for s in REPORTED]}")
