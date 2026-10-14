"""The explicit predicate algebra, executed: quantifiers over every collection
kind, single-valued traversal, relationship matching, and target-local subtype
tests.

Each expectation is the set of roots an independent reading of the stored rows
selects. Stored carriers the Typed write path never produces — JSON null, a
non-array, a wrong-kind or null element — are written out of band, because the
algebra's answer over them is part of its contract.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Iterable
from typing import Any, cast

import pytest

from parallax.core import (
    LATEST,
    MANY_TO_ONE,
    AbstractRoot,
    Attr,
    Bitemporal,
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
from parallax.snapshot import ScopedDatabase, Transaction, connect, is_view_loaded
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
    vehicles: Rel[tuple[Vehicle, ...]] = rel(reverse_of="owner")


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
    owner_id: Attr[int | None]
    owner: Rel[Owner | None] = rel(cardinality=MANY_TO_ONE, join=("owner_id", "id"))


class Car(Vehicle, table="pa_car", namespace=_NS, inheritance=ConcreteSubtype()):
    seats: Attr[int | None] = attr(type=Int32)


class Bike(Vehicle, table="pa_bike", namespace=_NS, inheritance=ConcreteSubtype()):
    gears: Attr[int | None] = attr(type=Int32)


class Parking(Entity, table="pa_parking", namespace=_NS):
    id: Attr[int] = attr(primary_key=True)
    vehicle_id: Attr[int | None]
    vehicle: Rel[Vehicle | None] = rel(cardinality=MANY_TO_ONE, join=("vehicle_id", "id"))


class Lease(Entity, table="pa_lease", namespace=_NS):
    id: Attr[int] = attr(primary_key=True)
    version: Attr[int] = attr(type=Int32, optimistic_locking=True)
    owner_id: Attr[int | None]
    owner: Rel[Owner | None] = rel(cardinality=MANY_TO_ONE, join=("owner_id", "id"))


class Ticket(Entity, table="pa_ticket", namespace=_NS):
    id: Attr[int] = attr(primary_key=True)
    parking_id: Attr[int | None]
    parking: Rel[Parking | None] = rel(cardinality=MANY_TO_ONE, join=("parking_id", "id"))


class Plan(Bitemporal, table="pa_plan", namespace=_NS):
    id: Attr[int] = attr(primary_key=True)
    premium: Attr[int] = attr(type=Int32)


class Policy(Bitemporal, table="pa_policy", namespace=_NS):
    id: Attr[int] = attr(primary_key=True)
    plan_id: Attr[int]
    note: Attr[str] = attr(max_length=8)
    plan: Rel[Plan] = rel(cardinality=MANY_TO_ONE, join=("plan_id", "id"))


class Desk(Entity, table="pa_desk", namespace=_NS):
    id: Attr[int] = attr(primary_key=True)
    plan_id: Attr[int | None]
    plan: Rel[Plan | None] = rel(cardinality=MANY_TO_ONE, join=("plan_id", "id"))


class Shelf(Entity, table="pa_shelf", namespace=_NS):
    id: Attr[int] = attr(primary_key=True)
    tags: Attr[tuple[str, ...]]
    scores: Attr[tuple[int, ...]] = attr(type=Int32)
    parcels: Attr[tuple[Parcel, ...]]


class Crate(Entity, table="pa_crate", namespace=_NS):
    id: Attr[int] = attr(primary_key=True)
    shelf_id: Attr[int | None]
    shelf: Rel[Shelf | None] = rel(cardinality=MANY_TO_ONE, join=("shelf_id", "id"))


class Bin(Entity, table="pa_bin", namespace=_NS):
    id: Attr[int] = attr(primary_key=True)
    version: Attr[int] = attr(type=Int32, optimistic_locking=True)
    shelf_id: Attr[int | None]
    shelf: Rel[Shelf | None] = rel(cardinality=MANY_TO_ONE, join=("shelf_id", "id"))


class Tariff(Bitemporal, table="pa_tariff", namespace=_NS):
    id: Attr[int] = attr(primary_key=True)
    codes: Attr[tuple[str, ...]]


class Counter(Entity, table="pa_counter", namespace=_NS):
    id: Attr[int] = attr(primary_key=True)
    tariff_id: Attr[int | None]
    tariff: Rel[Tariff | None] = rel(cardinality=MANY_TO_ONE, join=("tariff_id", "id"))


_MODEL = DomainModel(
    Owner,
    Basket,
    Vehicle,
    Car,
    Bike,
    Parking,
    Lease,
    Ticket,
    Plan,
    Policy,
    Desk,
    Shelf,
    Crate,
    Bin,
    Tariff,
    Counter,
)


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


def test_shared_to_one_joins_keep_three_valued_truth(profile_run: Any) -> None:
    db = _served(profile_run)
    _seed_baskets(db)
    owner = Basket.owner
    active = owner.active.is_(True)
    # Owner 2's unknown conjunction stays unknown under negation; the absent owner
    # makes it false, so its negation selects basket 3.
    assert _ids(db, Basket, ~(owner.exists() & active & (owner.nickname == "ace"))) == {3}
    assert _ids(db, Basket, owner.not_exists() | (owner.nickname == "ace")) == {1, 3}
    assert _ids(db, Basket, owner.nickname.is_null() | active) == {1, 2, 3}
    assert _ids(db, Basket, (owner.nickname != "zed") & ~(active | owner.active.is_null())) == set()
    # Matching beside a dotted field reads the shared owner: owner 2's unknown and
    # the absent owner do not match, unlike the negated dotted comparison.
    matched = owner.nickname.is_null() & owner.not_exists(Owner.active.is_(True))
    assert _ids(db, Basket, matched) == {2, 3}
    assert _ids(db, Basket, owner.nickname.is_null() & ~active) == set()
    assert _ids(db, Basket, (owner.nickname == "ace") & owner.exists(Owner.active.is_(True))) == {1}


def test_a_materializing_predicate_write_selects_through_shared_joins(profile_run: Any) -> None:
    db = _served(profile_run)
    _seed_baskets(db)
    db.transact(
        lambda tx: [
            tx.insert(Lease(id=lease, owner_id=owner))
            for lease, owner in ((1, 1), (2, 2), (3, None))
        ]
    )
    owner = Lease.owner
    # Owner 2's unknown nickname keeps lease 2 unselected; the absent owner selects 3.
    db.transact(
        lambda tx: tx.delete_where(Lease.where(~(owner.exists() & (owner.nickname == "ace"))))
    )
    assert _ids(db, Lease, owner.exists() | owner.not_exists()) == {1, 2}


def test_shared_joins_page_stream_and_lock_only_their_roots(profile_run: Any) -> None:
    db = _served(profile_run)
    _seed_baskets(db)
    db.transact(lambda tx: tx.insert(Basket(id=4, owner_id=1, tags=(), scores=(), parcels=())))
    query = Basket.where(Basket.owner.nickname.is_null() | Basket.owner.active.is_(True))
    ordered = query.order_by(Basket.owner_id.asc(), Basket.id.asc())
    eager = [basket.id for basket in db.find(ordered).results()]
    assert eager == [1, 4, 2, 3]
    with db.stream(ordered, batch_size=1) as streamed:
        assert [basket.id for basket in streamed] == eager
    assert [basket.id for basket in db.find(ordered.limit(2)).results()] == [1, 4]
    assert not any(is_view_loaded(basket, Basket.owner) for basket in db.find(query).results())

    def locked(tx: Transaction) -> list[int]:
        found = [basket.id for basket in tx.find(query.order_by(Basket.id.asc())).results()]
        control = profile_run.control()
        try:
            control.execute("select id from pa_owner where id = 1 for update nowait", [])
            with pytest.raises(Exception, match="could not obtain lock"):
                control.execute("select id from pa_basket where id = 1 for update nowait", [])
        finally:
            control.close()
        return found

    assert db.transact(locked, concurrency="locking") == [1, 2, 3, 4]


def _seed_parking(profile_run: Any, db: ScopedDatabase) -> None:
    db.transact(
        lambda tx: [
            tx.insert(Owner(id=1, active=True, nickname="ace")),
            tx.insert(Car(id=5, maker="Volvo", seats=4, owner_id=1)),
            tx.insert(Car(id=7, maker="Saab", seats=None, owner_id=None)),
            tx.insert(Bike(id=6, maker="Trek", gears=21, owner_id=1)),
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
    db.transact(lambda tx: tx.insert(Bike(id=5, maker="Twin", gears=3, owner_id=None)))
    _assert_ambiguous(db, Parking.vehicle.maker == "Volvo")


def _assert_ambiguous(
    db: ScopedDatabase, predicate: Predicate[Any], root: type[Entity] = Parking
) -> None:
    with pytest.raises(Exception) as raised:
        db.find(root.where(predicate)).results()
    cause: BaseException | None = raised.value
    while cause is not None and not isinstance(cause, DatabaseError):
        cause = cause.__cause__ or getattr(cause, "cause", None)
    assert isinstance(cause, DatabaseError)
    assert (cause.category, cause.native_code) == (None, "21000")


def test_a_relationship_match_tests_its_complete_operand_for_truth(profile_run: Any) -> None:
    db = _served(profile_run)
    _seed_baskets(db)
    active = Owner.active.is_(True)
    assert _ids(db, Basket, Basket.owner.exists(active)) == {1}
    # Owner 2's unknown and basket 3's absent owner match nothing.
    assert _ids(db, Basket, Basket.owner.not_exists(active)) == {2, 3}
    assert _ids(db, Basket, ~Basket.owner.exists(active)) == {2, 3}
    # A negated dotted comparison keeps both unknowns instead.
    assert _ids(db, Basket, ~Basket.owner.active.is_(True)) == set()
    either = active | Owner.nickname.is_null()
    assert _ids(db, Basket, Basket.owner.exists(either)) == {1, 2}
    assert _ids(db, Basket, Basket.owner.exists(~active)) == set()
    assert _ids(db, Basket, Basket.owner.exists() & ~Basket.owner.exists(active)) == {2}


def test_typed_and_wire_matches_select_the_same_roots(profile_run: Any) -> None:
    db = _served(profile_run)
    _seed_baskets(db)
    owner = f"{Basket.identity.canonical}.owner"
    document = {
        "target": Basket.identity.canonical,
        "predicate": {
            "notExists": {"path": owner, "where": {"eq": {"path": "active", "value": True}}}
        },
    }
    wire = {cast("Any", node)["id"] for node in db.wire.find(document).results()}
    assert wire == _ids(db, Basket, Basket.owner.not_exists(Owner.active.is_(True))) == {2, 3}


def test_a_relationship_match_is_existential_over_every_candidate(profile_run: Any) -> None:
    db = _served(profile_run)
    _seed_parking(profile_run, db)
    db.transact(lambda tx: tx.insert(Bike(id=5, maker="Twin", gears=3, owner_id=None)))
    # Parking 30 reaches both car 5 and bike 5: two candidates to match, not an ambiguity.
    assert _ids(db, Parking, Parking.vehicle.exists(Vehicle.maker == "Twin")) == {30}
    assert _ids(db, Parking, Parking.vehicle.not_exists(Vehicle.maker == "Twin")) == {31, 32, 33}
    roomy = Vehicle.is_a(Car, where=Car.seats > 2)
    assert _ids(db, Parking, Parking.vehicle.exists(roomy)) == {30}
    assert _ids(db, Parking, Parking.vehicle.exists(Vehicle.owner.active.is_(True))) == {30, 31}
    # A dotted prefix before the matched relationship still demands one candidate.
    _assert_ambiguous(db, Parking.vehicle.owner.exists(Owner.active.is_(True)))


def _seed_tickets(profile_run: Any, db: ScopedDatabase) -> None:
    _seed_parking(profile_run, db)
    db.transact(
        lambda tx: [
            tx.insert(Ticket(id=ticket, parking_id=parking))
            for ticket, parking in ((50, 30), (51, 31), (52, 32), (53, 33), (54, None))
        ]
    )


def test_a_hop_around_an_unproven_one_reads_through_the_shared_prefix(profile_run: Any) -> None:
    db = _served(profile_run)
    _seed_tickets(profile_run, db)
    active = Ticket.parking.vehicle.owner.active
    assert _ids(db, Ticket, active.is_(True)) == {50, 51}
    # A missing parking, vehicle, or owner leaves the field unknown at every hop.
    assert _ids(db, Ticket, active.is_null()) == {52, 53, 54}
    assert _ids(db, Ticket, ~active.is_(True)) == set()
    assert _ids(db, Ticket, Ticket.parking.vehicle.is_a(Car)) == {50, 53}
    roomy = Ticket.parking.vehicle.is_a(Car, where=Car.seats > 2)
    assert _ids(db, Ticket, ~roomy) == {51, 52, 54}
    assert _ids(db, Ticket, Ticket.parking.vehicle.exists(Vehicle.maker == "Trek")) == {51}


def test_the_unproven_hop_still_fails_on_two_candidates_the_ticket_reaches(
    profile_run: Any,
) -> None:
    db = _served(profile_run)
    _seed_tickets(profile_run, db)
    db.transact(lambda tx: tx.insert(Bike(id=5, maker="Twin", gears=3, owner_id=None)))
    # The twin reaches no owner and is not a car, yet it is the second candidate.
    _assert_ambiguous(db, Ticket.parking.vehicle.owner.active.is_(True), Ticket)
    _assert_ambiguous(db, Ticket.parking.vehicle.is_a(Car), Ticket)


def test_the_unproven_hop_never_reads_a_parking_no_ticket_reaches(profile_run: Any) -> None:
    db = _served(profile_run)
    _seed_tickets(profile_run, db)
    db.transact(
        lambda tx: [
            tx.insert(Car(id=9, maker="Volvo", seats=2, owner_id=None)),
            tx.insert(Bike(id=9, maker="Twin", gears=3, owner_id=None)),
            tx.insert(Parking(id=34, vehicle_id=9)),
        ]
    )
    # Parking 34's vehicle is ambiguous, but no ticket reaches it, so the strict
    # comparison over the joined parking cannot expose it to the vehicle hop.
    reached = (Ticket.parking.id > 0) & (Ticket.parking.vehicle.maker == "Volvo")
    assert _ids(db, Ticket, reached) == {50}


_JANUARY = dt.datetime(2024, 1, 1, tzinfo=dt.UTC)
_MARCH = dt.datetime(2024, 3, 1, tzinfo=dt.UTC)
_JUNE = dt.datetime(2024, 6, 1, tzinfo=dt.UTC)
_JULY = dt.datetime(2024, 7, 1, tzinfo=dt.UTC)


def _seed_plans(profile_run: Any) -> None:
    """Plan 1 was corrected in April: its first milestone overlaps the corrected
    two in Valid Time only, and those two are adjacent at June. Plan 2 never
    changed, and no plan 3 exists."""
    rows = (
        (1, 10, "2024-01-01", "infinity", "2024-01-01", "2024-04-01"),
        (1, 20, "2024-01-01", "2024-06-01", "2024-04-01", "infinity"),
        (1, 30, "2024-06-01", "infinity", "2024-04-01", "infinity"),
        (2, 20, "2024-01-01", "infinity", "2024-01-01", "infinity"),
    )
    current = "'2024-01-01', 'infinity', '2024-01-01', 'infinity'"
    _write(
        profile_run,
        (
            *(
                "insert into pa_plan (id, premium, from_z, thru_z, in_z, out_z) values "
                f"({plan}, {premium}, '{valid}', '{until}', '{since}', '{out}')"
                for plan, premium, valid, until, since, out in rows
            ),
            *(
                "insert into pa_policy (id, plan_id, note, from_z, thru_z, in_z, out_z) "
                f"values ({policy}, {policy}, 'n', {current})"
                for policy in (1, 2, 3)
            ),
            "insert into pa_desk (id, plan_id) values (1, 1), (2, 2), (3, 3), (4, null)",
        ),
    )


def _policies(db: ScopedDatabase, predicate: Predicate[Any], **pin: Any) -> list[int]:
    found = db.find(Policy.where(predicate).order_by(Policy.id.asc()).as_of(**pin)).results()
    return [policy.id for policy in found]


def test_a_temporal_hop_joins_the_one_milestone_each_coordinate_selects(
    profile_run: Any,
) -> None:
    db = _served(profile_run)
    _seed_plans(profile_run)
    premium = Policy.plan.premium
    latest = {"tx_time": LATEST, "valid_time": LATEST}
    assert _policies(db, premium == 30, **latest) == [1]
    assert _policies(db, premium == 20, **latest) == [2]
    assert _policies(db, premium == 20, tx_time=LATEST, valid_time=_MARCH) == [1, 2]
    # The corrected milestones are adjacent: June belongs to the later one alone.
    assert _policies(db, premium == 30, tx_time=LATEST, valid_time=_JUNE) == [1]
    assert _policies(db, premium >= 20, tx_time=LATEST, valid_time=_JUNE) == [1, 2]
    assert _policies(db, premium == 10, tx_time=_MARCH, valid_time=_MARCH) == [1]
    assert _policies(db, Policy.plan.not_exists(), tx_time=LATEST, valid_time=_MARCH) == [3]
    assert _policies(db, ~(premium == 20), tx_time=LATEST, valid_time=_JANUARY) == []


def test_temporal_joins_deliver_wire_streamed_and_paged_roots_alike(profile_run: Any) -> None:
    db = _served(profile_run)
    _seed_plans(profile_run)
    query = (
        Policy.where(Policy.plan.premium >= 20)
        .order_by(Policy.id.desc())
        .as_of(tx_time=LATEST, valid_time=_MARCH)
    )
    eager = [policy.id for policy in db.find(query).results()]
    assert eager == [2, 1]
    with db.stream(query, batch_size=1) as streamed:
        assert [policy.id for policy in streamed] == eager
    assert [policy.id for policy in db.find(query.limit(1)).results()] == [2]
    assert not any(is_view_loaded(policy, Policy.plan) for policy in db.find(query).results())
    document = {
        "target": Policy.identity.canonical,
        "predicate": {
            "greaterThanEquals": {"path": f"{Policy.identity.canonical}.plan.premium", "value": 20}
        },
        "temporal": {
            "transaction-time": {"asOf": "latest"},
            "valid-time": {"asOf": "2024-03-01T00:00:00.000000Z"},
        },
    }
    wire = sorted(cast("Any", node)["id"] for node in db.wire.find(document).results())
    assert wire == sorted(eager)


def test_a_locking_read_through_a_temporal_join_locks_only_its_roots(profile_run: Any) -> None:
    db = _served(profile_run)
    _seed_plans(profile_run)

    def locked(tx: Transaction) -> list[int]:
        query = Desk.where(Desk.plan.premium == 30).order_by(Desk.id.asc())
        found = [desk.id for desk in tx.find(query).results()]
        control = profile_run.control()
        try:
            control.execute("select id from pa_plan where id = 1 for update nowait", [])
            with pytest.raises(Exception, match="could not obtain lock"):
                control.execute("select id from pa_desk where id = 1 for update nowait", [])
        finally:
            control.close()
        return found

    assert db.transact(locked, concurrency="locking") == [1]


def test_a_temporal_predicate_write_acquires_through_the_temporal_join(profile_run: Any) -> None:
    db = _served(profile_run)
    _seed_plans(profile_run)
    db.transact(
        lambda tx: tx.amend_where(
            Policy.where(Policy.plan.premium == 30), Policy.note.set("top"), valid_from=_JULY
        )
    )
    found = db.find(
        Policy.where(Policy.note == "top").as_of(tx_time=LATEST, valid_time=_JULY)
    ).results()
    assert [policy.id for policy in found] == [1]


def _seed_shelves(profile_run: Any, db: ScopedDatabase) -> None:
    """Shelf 1 holds `a` and `b`, shelf 2 nothing; shelves 3 to 5, written out of
    band, hold a JSON null carrier, a non-array, and `a` beside a wrong-kind
    and a null element. Crates 1 and 2 share shelf 1; crate 7 has no shelf."""
    db.transact(
        lambda tx: [
            tx.insert(
                Shelf(
                    id=1,
                    tags=("a", "b"),
                    scores=(1, 2),
                    parcels=(Parcel(sku="p", qty=2, notes=()),),
                )
            ),
            tx.insert(Shelf(id=2, tags=(), scores=(), parcels=())),
        ]
    )
    _write(
        profile_run,
        [
            "insert into pa_shelf (id, tags, scores, parcels) values (3, 'null', '[]', '[]'), "
            "(4, '\"a\"', '[]', '[]'), (5, '[\"a\", 7, null]', '[]', '[]')",
            "insert into pa_crate (id, shelf_id) values "
            "(1, 1), (2, 1), (3, 2), (4, 3), (5, 4), (6, 5), (7, null)",
        ],
    )


def test_a_collection_an_owner_holds_answers_for_every_root_reaching_it(
    profile_run: Any,
) -> None:
    db = _served(profile_run)
    _seed_shelves(profile_run, db)
    tags = Crate.shelf.tags
    a, b = tags.element == "a", tags.element == "b"
    assert _ids(db, Crate, tags.any()) == {1, 2, 6}
    assert _ids(db, Crate, tags.none()) == {3, 4, 5, 7}
    assert _ids(db, Crate, tags.any(a)) == {1, 2, 6}
    assert _ids(db, Crate, tags.none(a)) == {3, 4, 5, 7}
    # A wrong-kind and a null element are candidates whose test is unknown.
    assert _ids(db, Crate, tags.all(tags.element.in_(["a", "b"]))) == {1, 2, 3, 4, 5, 7}
    assert _ids(db, Crate, tags.any(a) & tags.any(b)) == {1, 2}
    assert _ids(db, Crate, tags.any(a & b)) == set()
    assert _ids(db, Crate, tags.any(a) & ~Crate.shelf.exists()) == set()
    assert _ids(db, Crate, Crate.shelf.exists() & tags.none()) == {3, 4, 5}


def test_owner_results_deliver_wire_streamed_paged_and_root_locked_roots_alike(
    profile_run: Any,
) -> None:
    db = _served(profile_run)
    _seed_shelves(profile_run, db)
    query = Crate.where(Crate.shelf.tags.any(Crate.shelf.tags.element == "a"))
    ordered = query.order_by(Crate.id.asc())
    eager = [crate.id for crate in db.find(ordered).results()]
    assert eager == [1, 2, 6]
    with db.stream(ordered, batch_size=1) as streamed:
        assert [crate.id for crate in streamed] == eager
    assert [crate.id for crate in db.find(ordered.limit(2)).results()] == [1, 2]
    assert not any(is_view_loaded(crate, Crate.shelf) for crate in db.find(query).results())
    path = f"{Crate.identity.canonical}.shelf.tags"
    document = {
        "target": Crate.identity.canonical,
        "predicate": {"any": {"path": path, "where": {"eq": {"value": "a"}}}},
    }
    assert sorted(cast("Any", node)["id"] for node in db.wire.find(document).results()) == eager

    def locked(tx: Transaction) -> list[int]:
        found = [crate.id for crate in tx.find(ordered).results()]
        control = profile_run.control()
        try:
            control.execute("select id from pa_shelf where id = 1 for update nowait", [])
            with pytest.raises(Exception, match="could not obtain lock"):
                control.execute("select id from pa_crate where id = 1 for update nowait", [])
        finally:
            control.close()
        return found

    assert db.transact(locked, concurrency="locking") == eager


def test_a_cast_that_can_fail_reads_only_the_owners_a_root_reaches(profile_run: Any) -> None:
    db = _served(profile_run)
    _seed_shelves(profile_run, db)
    # Shelf 9's element and parcel quantity cannot convert to integers, and no
    # crate reaches it: the conversions stay with the crates that do.
    _write(
        profile_run,
        [
            "insert into pa_shelf (id, tags, scores, parcels) values "
            '(9, \'["a"]\', \'[1.5]\', \'[{"sku": "p", "qty": "x", "notes": []}]\')'
        ],
    )
    scores, parcels = Crate.shelf.scores, Crate.shelf.parcels
    assert _ids(db, Crate, scores.any(scores.element > 1)) == {1, 2}
    assert _ids(db, Crate, parcels.all(Parcel.qty > 1)) == {1, 2, 3, 4, 5, 6, 7}
    assert _ids(db, Crate, Crate.shelf.tags.any(Crate.shelf.tags.element == "a")) == {1, 2, 6}
    _write(profile_run, ["insert into pa_crate (id, shelf_id) values (8, 9)"])
    for failing in (scores.any(scores.element > 1), parcels.all(Parcel.qty > 1)):
        with pytest.raises(Exception) as raised:
            db.find(Crate.where(failing)).results()
        cause: BaseException | None = raised.value
        while cause is not None and not isinstance(cause, DatabaseError):
            cause = cause.__cause__ or getattr(cause, "cause", None)
        assert isinstance(cause, DatabaseError)
        assert cause.native_code == "22P02"


def test_a_related_collection_an_owner_holds_answers_at_the_joined_owner(
    profile_run: Any,
) -> None:
    db = _served(profile_run)
    _seed_parking(profile_run, db)
    db.transact(
        lambda tx: [
            tx.insert(Owner(id=2, active=None, nickname=None)),
            *(
                tx.insert(Lease(id=lease, owner_id=owner))
                for lease, owner in ((1, 1), (2, 2), (3, None))
            ),
        ]
    )
    vehicles = Lease.owner.vehicles
    assert _ids(db, Lease, vehicles.any(Vehicle.maker == "Trek")) == {1}
    assert _ids(db, Lease, vehicles.none()) == {2, 3}
    # The bike is outside the selection, so it is the universal's counterexample.
    assert _ids(db, Lease, vehicles.all(Vehicle.is_a(Car))) == {2, 3}
    assert _ids(db, Lease, vehicles.any(Vehicle.is_a(Car, where=Car.seats > 2))) == {1}
    assert _ids(db, Lease, vehicles.all(Vehicle.maker != "Saab")) == {1, 2, 3}


def _seed_tariffs(profile_run: Any) -> None:
    """Tariff 1 holds three milestones, only the last of them, coding `b`, at
    Latest; tariff 2 holds nothing. Counters 1 and 2 share tariff 1, and counter
    4 has none."""
    _write(
        profile_run,
        [
            "insert into pa_tariff (id, codes, from_z, thru_z, in_z, out_z) values "
            "(1, '[\"z\"]', '2024-01-01', 'infinity', '2024-01-01', '2024-04-01'), "
            "(1, '[\"a\"]', '2024-01-01', '2024-06-01', '2024-04-01', 'infinity'), "
            "(1, '[\"b\"]', '2024-06-01', 'infinity', '2024-04-01', 'infinity'), "
            "(2, '[]', '2024-01-01', 'infinity', '2024-01-01', 'infinity')",
            "insert into pa_counter (id, tariff_id) values (1, 1), (2, 1), (3, 2), (4, null)",
        ],
    )


def test_owner_results_read_the_one_milestone_a_temporal_owner_joins(profile_run: Any) -> None:
    db = _served(profile_run)
    _seed_tariffs(profile_run)
    codes = Counter.tariff.codes

    def counters(predicate: Predicate[Any]) -> list[int]:
        found = db.find(Counter.where(predicate).order_by(Counter.id.asc())).results()
        return [counter.id for counter in found]

    # Each milestone keeps its own result row, so a counter reads its tariff's
    # Latest codes once.
    assert counters(codes.any(codes.element == "b")) == [1, 2]
    assert counters(codes.any(codes.element.in_(["a", "z"]))) == []
    assert counters(codes.none()) == [3, 4]
    assert counters(codes.all(codes.element == "b")) == [1, 2, 3, 4]


def test_a_materializing_predicate_write_selects_through_owner_results(profile_run: Any) -> None:
    db = _served(profile_run)
    _seed_shelves(profile_run, db)
    db.transact(
        lambda tx: [
            tx.insert(Bin(id=bin_id, shelf_id=shelf))
            for bin_id, shelf in ((1, 1), (2, 2), (3, None))
        ]
    )
    db.transact(lambda tx: tx.delete_where(Bin.where(Bin.shelf.tags.none())))
    assert _ids(db, Bin, Bin.shelf.exists() | Bin.shelf.not_exists()) == {1}


def test_a_readless_write_selects_its_rows_through_shared_joins(profile_run: Any) -> None:
    db = _served(profile_run)
    _seed_baskets(db)
    owner = Basket.owner
    # Owner 2's unknown conjunction stays unknown under negation, so only the
    # basket with no owner is amended.
    negated = ~(owner.exists() & owner.active.is_(True) & (owner.nickname == "ace"))
    db.transact(lambda tx: tx.amend_where(Basket.where(negated), Basket.tags.set(("z",))))
    assert _ids(db, Basket, Basket.tags.any(Basket.tags.element == "z")) == {3}
    path = f"{Basket.identity.canonical}.owner"
    matched = {
        "and": {
            "operands": [
                {"isNull": {"path": f"{path}.alias"}},
                {"notExists": {"path": path, "where": {"eq": {"path": "active", "value": True}}}},
            ]
        }
    }
    db.transact(
        lambda tx: tx.wire.delete_where({"entity": Basket.identity.canonical, "predicate": matched})
    )
    assert _ids(db, Basket, owner.exists() | owner.not_exists()) == {1}


def test_a_readless_write_keeps_its_unproven_hop_s_cardinality_failure(profile_run: Any) -> None:
    db = _served(profile_run)
    _seed_tickets(profile_run, db)
    db.transact(
        lambda tx: [
            tx.insert(Car(id=9, maker="Volvo", seats=2, owner_id=None)),
            tx.insert(Bike(id=9, maker="Twin", gears=3, owner_id=None)),
            tx.insert(Parking(id=34, vehicle_id=9)),
        ]
    )
    # Parking 34's ambiguous vehicle is reached by no ticket, so the write never
    # evaluates it.
    reached = (Ticket.parking.id > 0) & (Ticket.parking.vehicle.maker == "Volvo")
    db.transact(lambda tx: tx.delete_where(Ticket.where(reached)))
    assert _ids(db, Ticket, Ticket.parking.exists() | Ticket.parking.not_exists()) == {
        51,
        52,
        53,
        54,
    }
    db.transact(lambda tx: tx.insert(Ticket(id=55, parking_id=34)))
    with pytest.raises(Exception) as raised:
        db.transact(lambda tx: tx.delete_where(Ticket.where(reached)))
    cause: BaseException | None = raised.value
    while cause is not None and not isinstance(cause, DatabaseError):
        cause = cause.__cause__ or getattr(cause, "cause", None)
    assert isinstance(cause, DatabaseError)
    assert (cause.category, cause.native_code) == (None, "21000")


def test_a_readless_write_converts_only_the_elements_of_owners_its_rows_reach(
    profile_run: Any,
) -> None:
    db = _served(profile_run)
    _seed_shelves(profile_run, db)
    _write(
        profile_run,
        ["insert into pa_shelf (id, tags, scores, parcels) values (9, '[\"a\"]', '[1.5]', '[]')"],
    )
    scores = Crate.shelf.scores
    # The occupancy test shares the shelf, so the write selects its keys; the
    # cast stays in its own hop, evaluated only for the shelf a crate reaches.
    failing = Crate.shelf.tags.any() & scores.any(scores.element > 1)
    db.transact(lambda tx: tx.delete_where(Crate.where(failing)))
    assert _ids(db, Crate, Crate.shelf.exists() | Crate.shelf.not_exists()) == {3, 4, 5, 6, 7}
    _write(profile_run, ["insert into pa_crate (id, shelf_id) values (8, 9)"])
    with pytest.raises(Exception) as raised:
        db.transact(lambda tx: tx.delete_where(Crate.where(failing)))
    cause: BaseException | None = raised.value
    while cause is not None and not isinstance(cause, DatabaseError):
        cause = cause.__cause__ or getattr(cause, "cause", None)
    assert isinstance(cause, DatabaseError)
    assert cause.native_code == "22P02"


def test_a_key_selecting_readless_write_stays_a_barrier(profile_run: Any) -> None:
    db = _served(profile_run)
    _seed_baskets(db)

    def fn(tx: Transaction) -> None:
        tx.insert(Owner(id=3, active=False, nickname="new"))
        tx.insert(Basket(id=4, owner_id=3, tags=(), scores=(), parcels=()))
        tx.delete_where(Basket.where(Basket.owner.nickname == "new"))
        tx.insert(Basket(id=5, owner_id=3, tags=(), scores=(), parcels=()))

    db.transact(fn)
    assert _ids(db, Basket, Basket.owner.nickname == "new") == {5}


def _desks(db: ScopedDatabase) -> set[int]:
    return _ids(db, Desk, Desk.plan.exists() | Desk.plan.not_exists())


def test_a_readless_write_selects_through_a_temporal_target_s_latest_milestone(
    profile_run: Any,
) -> None:
    db = _served(profile_run)
    _seed_plans(profile_run)
    premium = Desk.plan.premium
    # Plan 1's premiums 10 and 20 belong to milestones that are not Latest.
    db.transact(lambda tx: tx.amend_where(Desk.where(premium == 10), Desk.plan_id.set(None)))
    db.transact(lambda tx: tx.delete_where(Desk.where(premium == 30)))
    assert _desks(db) == {2, 3, 4}
    document = {
        "entity": Desk.identity.canonical,
        "predicate": {"eq": {"path": f"{Desk.identity.canonical}.plan.premium", "value": 20}},
    }
    db.transact(lambda tx: tx.wire.delete_where(document))
    assert _desks(db) == {3, 4}
    assert _ids(db, Desk, Desk.plan_id.is_null()) == {4}


def test_a_readless_write_matches_a_temporal_target_s_latest_milestone_in_place(
    profile_run: Any,
) -> None:
    db = _served(profile_run)
    _seed_plans(profile_run)
    plan = Desk.plan
    db.transact(lambda tx: tx.delete_where(Desk.where(plan.exists(Plan.premium == 10))))
    assert _desks(db) == {1, 2, 3, 4}
    # Desk 1's plan matches 20 only in a milestone that is not Latest; desk 3's
    # plan is absent and desk 4 has none.
    db.transact(lambda tx: tx.delete_where(Desk.where(plan.not_exists(Plan.premium == 20))))
    assert _desks(db) == {2}


def test_a_readless_write_reads_a_temporal_owner_s_latest_collection(profile_run: Any) -> None:
    db = _served(profile_run)
    _seed_tariffs(profile_run)
    codes = Counter.tariff.codes
    db.transact(lambda tx: tx.delete_where(Counter.where(codes.any(codes.element == "a"))))
    db.transact(lambda tx: tx.delete_where(Counter.where(codes.any(codes.element == "b"))))
    assert _ids(db, Counter, Counter.tariff.exists() | Counter.tariff.not_exists()) == {3, 4}
