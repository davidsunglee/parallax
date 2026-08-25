"""The canonical scenarios published-instance state is measured over, and the
fixture that builds one node the way publication builds it today.

COR-111's measurement contract names six scenarios — shallow, wide, nested,
nullable, partial, polymorphic — and asks for retained bytes on both sides of a
representation change. The "before" side has a problem the "after" side does not:
once publication attaches a compact tuple there is no legacy path left to measure,
so a comparison taken later would have nothing to compare against. This module is
that half, held as a fixture rather than as a number: :data:`SCENARIOS` names the
shapes, :func:`legacy_publication` builds one node the way Entity Graph
Construction builds one today, and :func:`disagreements` compares the fixture
against the real path so the fixture cannot quietly stop standing for it.

**Why the fixture is not ordinary construction.** A materialized node is
``cls.model_construct()`` with no arguments followed by one
``object.__setattr__`` per member, which leaves ``__pydantic_fields_set__``
permanently empty — the sharpest part of what publication currently retains, and
the part ordinary construction would not reproduce. A Value Object is different
and is reproduced differently: ``vo_class.model_construct(present, **values)``,
where ``present`` is exactly the members the row carried.

**What a scenario carries.** One positional member row, ``ABSENT``-spelled and
aligned to the exact Entity's ``EntityLayout`` — the same row a compiled read
lays out and hands across ``populate``'s door, with nested tuples at every Value
Object containment depth. Every leaf value is built once at import, outside every
measurement window, so a reading counts the positions a node holds and not the
payload it borrows.

Exported names carry no leading underscore: importing an underscored name across
modules is a `reportPrivateUsage` error under pyright strict, so privacy is
carried by this MODULE's underscore. Read by ``test_instance_state_baseline.py``
and by ``tools/instance_state_overhead.py``; never imported by production code.

This module deliberately avoids ``from __future__ import annotations`` so the
declaration engine reads the live ``Attr[T]`` / ``Rel[T]`` objects directly, as
``tests/_support/snapshot_models.py`` does for the same reason.
"""

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from decimal import Decimal
from functools import cached_property
from typing import Any, Final, cast

from pydantic import BaseModel

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
    EntityGraphWriter,
    NodeHandle,
    ResolutionView,
    graph_construction_of,
)
from parallax.core.entity._declaration import LIFECYCLE_STATE_SLOT, shape_of
from parallax.core.entity._entity import wire_names_of
from parallax.core.entity._layout import EntityLayout
from parallax.core.entity._model import DomainModel as ModelType
from parallax.core.entity._model import cataloged_model, class_index
from parallax.core.entity._pydantic_storage import instance_state
from parallax.core.entity._row import ABSENT, member_carriers
from parallax.core.metamodel import (
    EntityIdentity,
    Multiplicity,
    NestedValueObjectMetadata,
    ValueObjectMetadata,
)
from parallax.snapshot._inspection import SnapshotNodeState

__all__ = [
    "SCENARIOS",
    "LegacyArm",
    "LegacyPlan",
    "Scenario",
    "disagreements",
    "fingerprint",
    "legacy_publication",
    "published",
    "scenario_named",
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
# declaring none would understate both arms; one per scenario keeps that cost   #
# uniform across the mix and attributable to a single position.                 #
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
    """The ticket's directional nested shape: an Address carrying a Geo, and two
    Phone records under a Many occurrence."""

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


SHALLOW_MODEL: Final = DomainModel(Shallow)
WIDE_MODEL: Final = DomainModel(Wide)
NESTED_MODEL: Final = DomainModel(Nested)
OPTIONALS_MODEL: Final = DomainModel(Optionals)
VEHICLE_MODEL: Final = DomainModel(Vehicle, Wheeled, Car)


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


# --------------------------------------------------------------------------- #
# The two arms.                                                                #
# --------------------------------------------------------------------------- #

type LegacyArm = Callable[["Scenario", object | None], object]
"""How a scenario builds its legacy-shaped node, given its lifecycle state.

A field on the scenario rather than a module-level function so a test can hand
one arm a fixture that has stopped reproducing publication, which is what proves
:func:`disagreements` has teeth."""


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
    """One canonical shape, its input row, and the two arms that build it."""

    name: str
    summary: str
    model: ModelType
    entity: EntityIdentity
    values: tuple[object, ...]
    legacy: LegacyArm = field(default=lambda scenario, state: legacy_publication(scenario, state))

    @cached_property
    def layout(self) -> EntityLayout:
        """The exact Entity's member layout — the order ``values`` is read in."""
        return cataloged_model(self.model).layouts.entity(self.entity)

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
        object built outside the window would be borrowed by both arms and priced
        by neither.
        """
        return SnapshotNodeState(entity=self.entity, views={})


def published(scenario: Scenario, state: object | None) -> object:
    """``scenario``'s node through the real Entity Graph Construction path.

    The production route in full: the positional row translated by
    ``member_carriers`` — what the Snapshot materializer calls at the same door —
    handed to ``populate``, with the lifecycle state attached by a factory the way
    a materialization attaches one.
    """
    attributes, occurrences = member_carriers(scenario.layout, scenario.values)

    def build(writer: EntityGraphWriter) -> tuple[NodeHandle, ...]:
        handle = writer.allocate(scenario.entity)
        writer.populate(handle, attributes, occurrences, ())
        return (handle,)

    def factory(_view: ResolutionView, _handle: NodeHandle) -> object:
        return state

    construction = graph_construction_of(scenario.model)
    (root,) = construction.construct(build, state_factory=None if state is None else factory)
    return root


def legacy_publication(scenario: Scenario, state: object | None) -> object:
    """``scenario``'s node built the way publication builds one today.

    Zero-argument ``model_construct`` and one ``object.__setattr__`` per member,
    so the empty fields-set a materialized node carries is reproduced rather than
    approximated; every declared relationship slot written, since publication
    installs the unloaded sentinel where a read loaded nothing; and the lifecycle
    state written straight into the node's storage last, as the construction
    call's own final phase does.
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
        object.__setattr__(instance, py_name, UNLOADED)
    if state is not None:
        object.__setattr__(instance, LIFECYCLE_STATE_SLOT, state)
    return instance


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
# The reproduction check.                                                      #
# --------------------------------------------------------------------------- #


def fingerprint(value: object) -> object:
    """``value``'s whole physical state, as something two arms can be compared by.

    Every structure a reading prices and nothing a reading does not: the exact
    class, the instance storage reached past whatever the class binds, the
    Pydantic field set, and the extra and private slots — recursively, so a Value
    Object occurrence is compared the same way at every containment depth. Storage
    is compared as a mapping rather than as a sequence, because insertion order
    costs a published node nothing.
    """
    if isinstance(value, BaseModel):
        return (
            "model",
            f"{type(value).__module__}.{type(value).__qualname__}",
            _mapping(instance_state(value)),
            tuple(sorted(value.__pydantic_fields_set__)),
            fingerprint(value.__pydantic_extra__),
            fingerprint(value.__pydantic_private__),
        )
    if type(value) is tuple:
        return ("tuple", tuple(fingerprint(item) for item in cast("tuple[object, ...]", value)))
    if type(value) is dict:
        return ("dict", _mapping(cast("Mapping[str, object]", value)))
    return ("leaf", f"{type(value).__module__}.{type(value).__qualname__}", repr(value))


def _mapping(items: Mapping[str, object]) -> tuple[tuple[str, object], ...]:
    return tuple(
        sorted(
            ((str(name), fingerprint(item)) for name, item in items.items()),
            key=lambda pair: pair[0],
        )
    )


def disagreements(scenario: Scenario) -> tuple[str, ...]:
    """Where ``scenario``'s legacy arm and the real publication path differ.

    Empty while the fixture still stands for publication, which is the whole of
    what the frozen reading is worth: a number taken over an arm that has stopped
    reproducing the path it was taken to stand for describes nothing.

    Both lifecycle states are compared, because attaching one is a separate phase
    of a construction call and a fixture could reproduce either half alone.
    """
    findings: list[str] = []
    for carrying, state in (("with lifecycle state", scenario.state()), ("bare", None)):
        real = fingerprint(published(scenario, state))
        fixture = fingerprint(scenario.legacy(scenario, state))
        if real != fixture:
            findings.append(
                f"{scenario.name} ({carrying}): the legacy arm no longer reproduces "
                f"publication\n    published: {real}\n    fixture:   {fixture}"
            )
    return tuple(findings)


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


def scenario_named(name: str) -> Scenario:
    """The canonical scenario ``name`` names, or a loud rejection."""
    for scenario in SCENARIOS:
        if scenario.name == name:
            return scenario
    raise KeyError(f"{name!r} is not a canonical scenario: {[s.name for s in SCENARIOS]}")
