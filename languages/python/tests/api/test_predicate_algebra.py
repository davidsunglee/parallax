"""The explicit predicate algebra, executed: quantifiers over every collection
kind, single-valued traversal, and target-local subtype tests.

Each expectation is the set of roots an independent reading of the stored rows
selects. Stored carriers the Typed write path never produces — JSON null, a
non-array, a wrong-kind or null element — are written out of band, because the
algebra's answer over them is part of its contract.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any, cast

import pytest

from parallax.core import (
    MANY_TO_ONE,
    AbstractRoot,
    Attr,
    ConcreteSubtype,
    DomainModel,
    Entity,
    Int32,
    Predicate,
    Rel,
    ValueObject,
    attr,
    rel,
)
from parallax.core.db_error import DatabaseError
from parallax.core.entity._model import model_of
from parallax.core.metamodel import TablePerConcreteSubtype
from parallax.core.read_delivery import InvalidData
from parallax.snapshot import ScopedDatabase, connect
from tests._support.root_ownership import own_root

_NS = "predicate.algebra"


class Parcel(ValueObject):
    sku: Attr[str]
    qty: Attr[int | None] = attr(type=Int32)
    notes: Attr[tuple[str, ...]]


class Meta(ValueObject):
    labels: Attr[tuple[str, ...]]


class Owner(Entity, table="pa_owner", namespace=_NS):
    id: Attr[int] = attr(primary_key=True)
    active: Attr[bool | None]
    nickname: Attr[str | None] = attr(name="alias", max_length=16)


class Basket(Entity, table="pa_basket", namespace=_NS):
    id: Attr[int] = attr(primary_key=True)
    owner_id: Attr[int | None]
    tags: Attr[tuple[str, ...]]
    scores: Attr[tuple[int, ...]] = attr(type=Int32)
    parcels: Attr[tuple[Parcel, ...]]
    extra: Attr[Meta | None]
    owner: Rel[Owner | None] = rel(cardinality=MANY_TO_ONE, join=("owner_id", "id"))


class Vehicle(Entity, namespace=_NS, inheritance=AbstractRoot(TablePerConcreteSubtype())):
    id: Attr[int] = attr(primary_key=True)
    maker: Attr[str] = attr(max_length=16)


class Car(Vehicle, table="pa_car", namespace=_NS, inheritance=ConcreteSubtype()):
    seats: Attr[int | None] = attr(type=Int32)


class Bike(Vehicle, table="pa_bike", namespace=_NS, inheritance=ConcreteSubtype()):
    gears: Attr[int | None] = attr(type=Int32)


class Parking(Entity, table="pa_parking", namespace=_NS):
    id: Attr[int] = attr(primary_key=True)
    vehicle_id: Attr[int | None]
    vehicle: Rel[Vehicle | None] = rel(cardinality=MANY_TO_ONE, join=("vehicle_id", "id"))


_MODEL = DomainModel(Owner, Basket, Vehicle, Car, Bike, Parking)


def _served(profile_run: Any) -> ScopedDatabase:
    profile_run.reset(model_of(_MODEL), {})
    return own_root(connect(profile_run.port, _MODEL)).using_database_login()


def _write(profile_run: Any, statements: Iterable[str]) -> None:
    control = profile_run.control()
    try:
        for statement in statements:
            control.execute_write(statement, [])
    finally:
        control.close()


def _ids(db: ScopedDatabase, root: type[Entity], predicate: Predicate[Any]) -> set[int]:
    """The ids of the roots ``predicate`` selects, read in band so a root whose
    stored collection is invalid still answers with its key."""
    selected: set[int] = set()
    for record in db.find(root.where(predicate)).checked().results():
        if isinstance(record, InvalidData):
            assert record.object_key is not None
            selected.add(int(cast("int", dict(record.object_key.primary_key)["id"])))
        else:
            selected.add(cast("Any", record).id)
    return selected


def _seed_baskets(db: ScopedDatabase) -> None:
    db.transact(
        lambda tx: [
            tx.insert(Owner(id=1, active=True, nickname="ace")),
            tx.insert(Owner(id=2, active=None, nickname=None)),
            tx.insert(
                Basket(
                    id=1,
                    owner_id=1,
                    tags=("a", "b"),
                    scores=(1, 2),
                    parcels=(
                        Parcel(sku="p", qty=2, notes=("fragile",)),
                        Parcel(sku="q", qty=None, notes=()),
                    ),
                    extra=Meta(labels=("x",)),
                )
            ),
            tx.insert(Basket(id=2, owner_id=2, tags=(), scores=(), parcels=(), extra=None)),
            tx.insert(
                Basket(
                    id=3,
                    owner_id=None,
                    tags=("c",),
                    scores=(5,),
                    parcels=(Parcel(sku="p", qty=7, notes=("cold", "fragile")),),
                    extra=Meta(labels=()),
                )
            ),
        ]
    )


def test_scalar_quantifiers_read_each_element_by_its_declared_type(profile_run: Any) -> None:
    db = _served(profile_run)
    _seed_baskets(db)
    tag = Basket.tags.element
    assert _ids(db, Basket, Basket.tags.any()) == {1, 3}
    assert _ids(db, Basket, Basket.tags.none()) == {2}
    assert _ids(db, Basket, Basket.tags.any(tag == "a")) == {1}
    assert _ids(db, Basket, Basket.tags.none(tag == "a")) == {2, 3}
    assert _ids(db, Basket, Basket.tags.all(tag.in_(["a", "b"]))) == {1, 2}
    # A nonempty universal is the explicit conjunction of occupancy and `all`.
    assert _ids(db, Basket, Basket.tags.any() & Basket.tags.all(tag.in_(["a", "b"]))) == {1}
    assert _ids(db, Basket, Basket.scores.any(Basket.scores.element.between(2, 5))) == {1, 3}
    assert _ids(db, Basket, Basket.tags.any(tag.starts_with("c"))) == {3}
    assert _ids(db, Basket, ~Basket.tags.any(~(tag == "a"))) == {2}


def test_separate_quantifiers_bind_separate_elements(profile_run: Any) -> None:
    db = _served(profile_run)
    _seed_baskets(db)
    same = Basket.parcels.any((Parcel.sku == "q") & (Parcel.qty == 2))
    separate = Basket.parcels.any(Parcel.sku == "q") & Basket.parcels.any(Parcel.qty == 2)
    assert _ids(db, Basket, same) == set()
    assert _ids(db, Basket, separate) == {1}


def test_quantifiers_nest_through_value_object_elements(profile_run: Any) -> None:
    db = _served(profile_run)
    _seed_baskets(db)
    fragile = Parcel.notes.any(Parcel.notes.element == "fragile")
    assert _ids(db, Basket, Basket.parcels.any(fragile)) == {1, 3}
    assert _ids(db, Basket, Basket.parcels.all(fragile)) == {2, 3}
    # A collection reached through an absent single Value Object holds nothing.
    assert _ids(db, Basket, Basket.extra.labels.none()) == {2, 3}
    assert _ids(db, Basket, Basket.extra.labels.any(Basket.extra.labels.element == "x")) == {1}
    assert _ids(db, Basket, Basket.extra.exists()) == {1, 3}


def test_json_null_and_non_array_carriers_hold_no_elements(
    profile_run: Any,
) -> None:
    db = _served(profile_run)
    _write(
        profile_run,
        [
            "insert into pa_basket (id, tags, scores, parcels) "
            "values (5, 'null', '[]', '[]'), "
            "(6, '\"a\"', '[]', '[]'), (7, '{\"0\": \"a\"}', '[]', '[]')",
        ],
    )
    tag = Basket.tags.element
    assert _ids(db, Basket, Basket.tags.any()) == set()
    assert _ids(db, Basket, Basket.tags.none()) == {5, 6, 7}
    assert _ids(db, Basket, Basket.tags.any(tag == "a")) == set()
    assert _ids(db, Basket, Basket.tags.all(tag == "z")) == {5, 6, 7}


def test_a_wrong_kind_or_null_element_is_an_unknown_candidate(profile_run: Any) -> None:
    db = _served(profile_run)
    _write(
        profile_run,
        [
            "insert into pa_basket (id, tags, scores, parcels) values "
            "(1, '[]', '[1, \"1\", null]', '[]'), (2, '[]', '[1]', '[]')",
        ],
    )
    one = Basket.scores.element == 1
    assert _ids(db, Basket, Basket.scores.any(one)) == {1, 2}
    assert _ids(db, Basket, Basket.scores.all(one)) == {2}
    assert _ids(db, Basket, Basket.scores.none(~one)) == {1, 2}
    assert _ids(db, Basket, Basket.scores.any(~one)) == set()
    # A true disjunct makes the complete element predicate true despite the
    # other term's unknown.
    assert _ids(db, Basket, Basket.scores.all(one | (Basket.scores.element > 0))) == {2}
    assert _ids(db, Basket, Basket.scores.any()) == {1, 2}


def test_single_valued_traversal_reads_one_related_object(profile_run: Any) -> None:
    db = _served(profile_run)
    _seed_baskets(db)
    assert _ids(db, Basket, Basket.owner.active.is_(True)) == {1}
    assert _ids(db, Basket, ~Basket.owner.active.is_(True)) == set()
    assert _ids(db, Basket, Basket.owner.exists()) == {1, 2}
    assert _ids(db, Basket, Basket.owner.not_exists()) == {3}
    assert _ids(db, Basket, Basket.owner.nickname == "ace") == {1}
    assert _ids(db, Basket, Basket.owner.nickname.is_null()) == {2, 3}


def _seed_parking(profile_run: Any, db: ScopedDatabase) -> None:
    db.transact(
        lambda tx: [
            tx.insert(Car(id=5, maker="Volvo", seats=4)),
            tx.insert(Car(id=7, maker="Saab", seats=None)),
            tx.insert(Bike(id=6, maker="Trek", gears=21)),
            tx.insert(Parking(id=30, vehicle_id=5)),
            tx.insert(Parking(id=31, vehicle_id=6)),
            tx.insert(Parking(id=32, vehicle_id=None)),
            tx.insert(Parking(id=33, vehicle_id=7)),
        ]
    )


def test_a_target_local_subtype_test_reads_the_reached_target(profile_run: Any) -> None:
    db = _served(profile_run)
    _seed_parking(profile_run, db)
    assert _ids(db, Parking, Parking.vehicle.is_a(Car)) == {30, 33}
    assert _ids(db, Parking, ~Parking.vehicle.is_a(Car)) == {31, 32}
    roomy = Parking.vehicle.is_a(Car, where=Car.seats > 2)
    assert _ids(db, Parking, roomy) == {30}
    # Absent or unselected targets are false; a selected one keeps its unknown.
    assert _ids(db, Parking, ~roomy) == {31, 32}
    assert _ids(db, Parking, Parking.vehicle.maker == "Trek") == {31}


def test_a_to_one_hop_reaching_two_candidates_fails_in_the_database(profile_run: Any) -> None:
    db = _served(profile_run)
    _seed_parking(profile_run, db)
    db.transact(lambda tx: tx.insert(Bike(id=5, maker="Twin", gears=3)))
    with pytest.raises(Exception) as raised:
        db.find(Parking.where(Parking.vehicle.maker == "Volvo")).results()
    cause: BaseException | None = raised.value
    while cause is not None and not isinstance(cause, DatabaseError):
        cause = cause.__cause__ or getattr(cause, "cause", None)
    assert isinstance(cause, DatabaseError)
    assert (cause.category, cause.native_code) == (None, "21000")
