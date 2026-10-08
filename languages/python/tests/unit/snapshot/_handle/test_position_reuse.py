"""Which position resolutions each real Typed and Wire operation performs.

Model formation reads every root's family declaration sequence and precomputes
every Entity's own position; read planning then reuses those answers, resolving
only a query-wide narrowing and the one Storage Layout position its read arm
projects. Counting wrappers over the two facets' resolving methods
observe that through the production entrypoints against a live database: they
are installed before the model forms, so formation's own reads are visible, and
cleared before each operation, so the counts are that operation's alone.
"""

# pyright: reportPrivateUsage=false

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import Any, Literal

import pytest

from parallax.core import (
    AbstractRoot,
    Attr,
    ConcreteSubtype,
    DomainModel,
    Entity,
    TablePerHierarchy,
    ValueObject,
    attr,
)
from parallax.core.entity._model import model_of
from parallax.core.execution import (
    ServingModel,
    prepare_model,
)
from parallax.core.inheritance import InheritanceError
from parallax.core.inheritance._facet import _InheritanceFacet
from parallax.core.metamodel import EntityIdentity, TablePerConcreteSubtype
from parallax.core.storage_layout._facet import _StorageLayoutFacet
from parallax.snapshot import Database, ScopedDatabase, Transaction, connect
from tests._support.root_ownership import own_root

_NAMESPACE = "position.reuse"


class Note(ValueObject):
    text: Attr[str]


class Creature(
    Entity,
    table="reuse_creature",
    namespace=_NAMESPACE,
    inheritance=AbstractRoot(TablePerHierarchy(tag_column="kind")),
):
    id: Attr[int] = attr(primary_key=True)
    name: Attr[str]
    note: Attr[Note]


class Bird(Creature, namespace=_NAMESPACE, inheritance=ConcreteSubtype(tag_value="bird")):
    wingspan: Attr[int | None]


class Fish(Creature, namespace=_NAMESPACE, inheritance=ConcreteSubtype(tag_value="fish")):
    fins: Attr[int | None]


class Vehicle(
    Entity,
    namespace=_NAMESPACE,
    inheritance=AbstractRoot(TablePerConcreteSubtype()),
):
    id: Attr[int] = attr(primary_key=True)
    name: Attr[str]
    note: Attr[Note]


class Car(Vehicle, table="reuse_car", namespace=_NAMESPACE, inheritance=ConcreteSubtype()):
    doors: Attr[int]


class Boat(Vehicle, table="reuse_boat", namespace=_NAMESPACE, inheritance=ConcreteSubtype()):
    hulls: Attr[int]


class Ledger(Entity, table="reuse_ledger", namespace=_NAMESPACE):
    id: Attr[int] = attr(primary_key=True)
    balance: Attr[int]
    version: Attr[int] = attr(optimistic_locking=True)
    note: Attr[Note]


_CLASSES = (Creature, Bird, Fish, Vehicle, Car, Boat, Ledger)
_ROOTS = frozenset(EntityIdentity(_NAMESPACE, name) for name in ("Creature", "Vehicle", "Ledger"))

type Representation = Literal["typed", "wire"]
_REPRESENTATIONS: tuple[Representation, ...] = ("typed", "wire")


@dataclass(frozen=True, slots=True)
class _Counts:
    inheritance_position: int
    storage_position: int
    family: int


@dataclass(slots=True)
class _Spies:
    """What each counted facet method was asked since the last :meth:`clear`."""

    inheritance_position: list[object] = field(default_factory=list[object])
    storage_position: list[object] = field(default_factory=list[object])
    family: list[object] = field(default_factory=list[object])

    def clear(self) -> None:
        self.inheritance_position.clear()
        self.storage_position.clear()
        self.family.clear()

    def counts(self) -> _Counts:
        return _Counts(len(self.inheritance_position), len(self.storage_position), len(self.family))


def _recording(real: Callable[[Any, Any], Any], calls: list[object]) -> Callable[[Any, Any], Any]:
    def recorded(facet: object, argument: object) -> Any:
        calls.append(argument)
        return real(facet, argument)

    return recorded


@pytest.fixture
def spies(monkeypatch: pytest.MonkeyPatch) -> _Spies:
    recorded = _Spies()
    for owner, name, calls in (
        (_InheritanceFacet, "position", recorded.inheritance_position),
        (_InheritanceFacet, "family", recorded.family),
        (_StorageLayoutFacet, "position", recorded.storage_position),
    ):
        monkeypatch.setattr(owner, name, _recording(getattr(owner, name), calls))
    return recorded


def _note(text: str) -> Note:
    return Note(text=text)


def _seed(tx: Transaction) -> None:
    tx.insert(Bird(id=1, name="wren", note=_note("small"), wingspan=20))
    tx.insert(Fish(id=2, name="pike", note=_note("fast"), fins=7))
    tx.insert(Car(id=1, name="coupe", note=_note("red"), doors=2))
    tx.insert(Boat(id=2, name="skiff", note=_note("wooden"), hulls=1))
    tx.insert(Ledger(id=1, balance=10, note=_note("opening")))


@dataclass(frozen=True, slots=True)
class _Served:
    root: Database[Any]
    db: ScopedDatabase

    def misses(self) -> int:
        """The handle's own read-plan cache census."""
        return self.root._resources.planner._statistics().misses


def _served(profile_run: Any, spies: _Spies) -> _Served:
    """A fresh handle over a freshly formed and prepared model, seeded outside
    every counted window.

    Formation is the only stage that reads family declaration sequences, and it reads one for
    every root; preparation reuses the accepted model and resolves nothing.
    """
    model = DomainModel(*_CLASSES)
    assert set(spies.family) == _ROOTS
    spies.clear()
    prepared = prepare_model(model, edition="position-reuse")
    assert spies.counts() == _Counts(0, 0, 0)
    profile_run.reset(model_of(model), {})
    serving = ServingModel(prepared)
    own_root(connect(profile_run.port, serving)).using_database_login().transact(_seed)
    root = own_root(connect(profile_run.port, serving))
    return _Served(root, root.using_database_login())


# --------------------------------------------------------------------------- #
# Reads: one compile per read-plan cache miss.                                #
# --------------------------------------------------------------------------- #
@dataclass(frozen=True, slots=True)
class _Read:
    typed: Callable[[], Any]
    wire: dict[str, object]
    counts: _Counts
    rows: tuple[tuple[str, int, str], ...]


def _wire_query(target: str, *, narrow_to: str | None = None) -> dict[str, object]:
    query: dict[str, object] = {
        "target": f"{_NAMESPACE}.{target}",
        "predicate": {"greaterThanEquals": {"attr": f"{_NAMESPACE}.{target}.id", "value": 1}},
    }
    if narrow_to is not None:
        query["narrowTo"] = [f"{_NAMESPACE}.{narrow_to}"]
    return query


_READS: dict[str, _Read] = {
    "tph-root": _Read(
        lambda: Creature.where(Creature.id >= 1),
        _wire_query("Creature"),
        _Counts(0, 1, 0),
        (("Bird", 1, "small"), ("Fish", 2, "fast")),
    ),
    "tph-narrowed": _Read(
        lambda: Creature.where(Creature.id >= 1).narrow(Fish),
        _wire_query("Creature", narrow_to="Fish"),
        _Counts(1, 1, 0),
        (("Fish", 2, "fast"),),
    ),
    "tpcs-root": _Read(
        lambda: Vehicle.where(Vehicle.id >= 1),
        _wire_query("Vehicle"),
        _Counts(0, 1, 0),
        (("Boat", 2, "wooden"), ("Car", 1, "red")),
    ),
    "tpcs-narrowed": _Read(
        lambda: Vehicle.where(Vehicle.id >= 1).narrow(Car),
        _wire_query("Vehicle", narrow_to="Car"),
        _Counts(1, 1, 0),
        (("Car", 1, "red"),),
    ),
    "standalone": _Read(
        lambda: Ledger.where(Ledger.id >= 1),
        _wire_query("Ledger"),
        _Counts(0, 1, 0),
        (("Ledger", 1, "opening"),),
    ),
}


def _typed_row(root: Any) -> tuple[str, int, str]:
    return type(root).__name__, root.id, root.note.text


def _wire_row(node: Any, read: _Read) -> tuple[str, int, str]:
    standalone = str(read.wire["target"]).rpartition(".")[2]
    return node.get("familyVariant", standalone), node["id"], node["note"]["text"]


def _sorted(rows: Sequence[tuple[str, int, str]]) -> tuple[tuple[str, int, str], ...]:
    return tuple(sorted(rows))


@pytest.mark.parametrize("shape", sorted(_READS))
@pytest.mark.parametrize("representation", _REPRESENTATIONS)
def test_an_eager_read_resolves_only_what_its_plan_has_not(
    profile_run: Any, spies: _Spies, representation: Representation, shape: str
) -> None:
    read = _READS[shape]
    served = _served(profile_run, spies)
    db = served.db
    spies.clear()

    if representation == "typed":
        rows = [_typed_row(root) for root in db.find(read.typed()).results()]
    else:
        rows = [_wire_row(node, read) for node in db.wire.find(read.wire).results()]

    assert spies.counts() == read.counts
    assert served.misses() == 1
    assert _sorted(rows) == read.rows


@pytest.mark.parametrize("shape", sorted(_READS))
@pytest.mark.parametrize("representation", _REPRESENTATIONS)
def test_a_single_page_stream_resolves_only_what_its_plan_has_not(
    profile_run: Any, spies: _Spies, representation: Representation, shape: str
) -> None:
    read = _READS[shape]
    served = _served(profile_run, spies)
    db = served.db
    spies.clear()

    if representation == "typed":
        with db.stream(read.typed(), batch_size=10) as stream:
            rows = [_typed_row(root) for root in stream]
    else:
        with db.wire.stream(read.wire, batch_size=10) as stream:
            rows = [_wire_row(node, read) for node in stream]

    assert spies.counts() == read.counts
    assert served.misses() == 1
    assert _sorted(rows) == read.rows


# --------------------------------------------------------------------------- #
# Writes: keyed ingress resolves nothing; a materializing predicate write     #
# compiles its resolving read outside the read-plan cache.                    #
# --------------------------------------------------------------------------- #
_INSERTS: dict[str, tuple[Callable[[], Entity], str, dict[str, object]]] = {
    "standalone": (
        lambda: Ledger(id=2, balance=5, note=_note("second")),
        "Ledger",
        {"id": 2, "balance": 5, "note": {"text": "second"}},
    ),
    "tph-concrete": (
        lambda: Bird(id=3, name="kite", note=_note("second"), wingspan=90),
        "Bird",
        {"id": 3, "name": "kite", "note": {"text": "second"}, "wingspan": 90},
    ),
    "tpcs-concrete": (
        lambda: Boat(id=3, name="raft", note=_note("second"), hulls=2),
        "Boat",
        {"id": 3, "name": "raft", "note": {"text": "second"}, "hulls": 2},
    ),
}


@pytest.mark.parametrize("target", sorted(_INSERTS))
@pytest.mark.parametrize("representation", _REPRESENTATIONS)
def test_a_keyed_insert_resolves_no_position(
    profile_run: Any, spies: _Spies, representation: Representation, target: str
) -> None:
    typed, entity, data = _INSERTS[target]
    served = _served(profile_run, spies)
    db = served.db
    spies.clear()

    if representation == "typed":
        db.transact(lambda tx: tx.insert(typed()))
    else:
        db.transact(lambda tx: tx.wire.insert(f"{_NAMESPACE}.{entity}", data))

    assert spies.counts() == _Counts(0, 0, 0)
    assert served.misses() == 0
    committed = db.wire.find(
        {
            "target": f"{_NAMESPACE}.{entity}",
            "predicate": {"eq": {"attr": f"{_NAMESPACE}.{entity}.id", "value": data["id"]}},
        }
    ).result()
    assert {name: committed[name] for name in data} == data


@pytest.mark.parametrize("representation", _REPRESENTATIONS)
def test_a_materializing_predicate_update_resolves_one_storage_position(
    profile_run: Any, spies: _Spies, representation: Representation
) -> None:
    served = _served(profile_run, spies)
    db = served.db
    spies.clear()

    def update(tx: Transaction) -> None:
        if representation == "typed":
            tx.amend_where(Ledger.where(Ledger.id == 1), Ledger.balance.set(25))
        else:
            tx.wire.amend_where(
                {
                    "entity": f"{_NAMESPACE}.Ledger",
                    "predicate": {"eq": {"attr": f"{_NAMESPACE}.Ledger.id", "value": 1}},
                },
                {"balance": 25},
            )

    db.transact(update)

    assert spies.counts() == _Counts(0, 1, 0)
    assert served.misses() == 0
    committed = db.find(Ledger.where(Ledger.id == 1)).result()
    assert (committed.balance, committed.version) == (25, 2)


_FAMILY_TARGETS: dict[
    str, tuple[Callable[[Transaction], None], str, dict[str, object], dict[str, object]]
] = {
    "tph-concrete": (
        lambda tx: tx.amend_where(Bird.where(Bird.id == 1), Bird.wingspan.set(30)),
        "Bird",
        {"wingspan": 30},
        {"wingspan": 20},
    ),
    "tpcs-concrete": (
        lambda tx: tx.amend_where(Car.where(Car.id == 1), Car.doors.set(4)),
        "Car",
        {"doors": 4},
        {"doors": 2},
    ),
}


@pytest.mark.parametrize("target", sorted(_FAMILY_TARGETS))
@pytest.mark.parametrize("representation", _REPRESENTATIONS)
def test_a_family_predicate_update_is_refused_before_any_position_is_resolved(
    profile_run: Any, spies: _Spies, representation: Representation, target: str
) -> None:
    typed, entity, changes, seeded = _FAMILY_TARGETS[target]
    selection: dict[str, object] = {
        "entity": f"{_NAMESPACE}.{entity}",
        "predicate": {"eq": {"attr": f"{_NAMESPACE}.{entity}.id", "value": 1}},
    }
    served = _served(profile_run, spies)
    db = served.db
    spies.clear()
    refusals: list[InheritanceError] = []

    def update(tx: Transaction) -> None:
        with pytest.raises(InheritanceError) as caught:
            if representation == "typed":
                typed(tx)
            else:
                tx.wire.amend_where(selection, changes)
        refusals.append(caught.value)

    db.transact(update)

    assert spies.counts() == _Counts(0, 0, 0)
    assert [refusal.rule for refusal in refusals] == ["subtype-write-set-based-unsupported"]
    committed = db.wire.find(
        {"target": selection["entity"], "predicate": selection["predicate"]}
    ).result()
    assert {name: committed[name] for name in seeded} == seeded
