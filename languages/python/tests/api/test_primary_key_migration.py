"""Coordinated migrations of native allocators, deployed against real Postgres.

Each story stores keys and reserves blocks under the earlier edition, drains
its root, applies the migration `coordinated_migration` generates — performing
each manual step itself — and opens a replacement root under the later edition,
whose first keyless insert must land past everything the earlier one stored or
reserved.
"""

from __future__ import annotations

from contextlib import closing
from typing import Any

from parallax.core import (
    AbstractRoot,
    Attr,
    ConcreteSubtype,
    DomainModel,
    Entity,
    KeySequence,
    TxTemporal,
    attr,
)
from parallax.core.internal.dialect import POSTGRES
from parallax.core.internal.entity._model import model_of
from parallax.core.internal.metamodel import TablePerConcreteSubtype
from parallax.evolution import (
    CoordinatedEvolution,
    CoordinatedMigration,
    ManualAction,
    ManualStep,
    coordinated_migration,
    evolve,
)
from parallax.postgres import PostgresBinding, PostgresLocation, PostgresTable
from parallax.snapshot import TxnContext, connect
from tests._support.root_ownership import own_root

_NAMESPACE = "key.migration"
_PX = PostgresBinding(default=PostgresLocation(schema="px"))
_BINDING = PostgresBinding(
    default=PostgresLocation(schema="px"),
    entities={
        f"{_NAMESPACE}.Truck": PostgresTable(schema="px_eu"),
        f"{_NAMESPACE}.Van": PostgresTable(schema="px_us"),
    },
)


def _fleet(key: KeySequence | bool) -> tuple[DomainModel, type[Any], type[Any], type[Any]]:
    """One edition of a table-per-concrete-subtype fleet, its leaves in two
    schemas, beside a Transaction-Time depot; every key is ``key``."""

    class Fleet(Entity, namespace=_NAMESPACE, inheritance=AbstractRoot(TablePerConcreteSubtype())):
        id: Attr[int] = attr(primary_key=key)
        label: Attr[str] = attr(max_length=8)

    class Truck(Fleet, table="mig_vehicle", namespace=_NAMESPACE, inheritance=ConcreteSubtype()):
        axles: Attr[int | None]

    class Van(Fleet, table="mig_vehicle", namespace=_NAMESPACE, inheritance=ConcreteSubtype()):
        doors: Attr[int | None]

    class Depot(TxTemporal, table="mig_depot", namespace=_NAMESPACE):
        id: Attr[int] = attr(primary_key=key)
        label: Attr[str] = attr(max_length=8)

    return DomainModel(Fleet, Truck, Van, Depot), Truck, Van, Depot


def _coupons(batch_size: int) -> tuple[DomainModel, type[Any]]:
    class Coupon(Entity, table="mig_coupon", namespace=_NAMESPACE):
        id: Attr[int] = attr(primary_key=KeySequence("mig_coupon_ids", batch_size=batch_size))
        label: Attr[str] = attr(max_length=8)

    return DomainModel(Coupon), Coupon


def _migration(
    earlier: DomainModel, later: DomainModel, binding: PostgresBinding
) -> CoordinatedMigration:
    evolution = evolve(earlier, later, earlier_binding=binding, later_binding=binding)
    assert isinstance(evolution, CoordinatedEvolution)
    return coordinated_migration(evolution)


def _deploy(profile_run: Any, migration: CoordinatedMigration) -> None:
    """Apply every generated statement in order. The one manual step these
    stories need is the drain, which each performed by closing its earlier
    root before this runs."""
    assert {step.action for step in migration.steps if isinstance(step, ManualStep)} == {
        ManualAction.DRAIN_EARLIER_ROOTS
    }
    assert isinstance(migration.steps[0], ManualStep)
    role = POSTGRES.quote(profile_run.default_role.name)
    with closing(profile_run.control()) as control:
        for step in migration.steps:
            if not isinstance(step, ManualStep):
                control.execute_write(step.sql, [])
        # Provisioning access stays the deployment's: a created sequence is
        # granted to the login that reserves from it.
        control.execute_write(f"grant usage on all sequences in schema px to {role}", [])


def _rows(profile_run: Any, sql: str) -> list[tuple[object, ...]]:
    return [tuple(row) for row in profile_run.port.execute(sql, [])]


def test_a_populated_family_and_its_history_join_a_new_allocator_past_every_stored_key(
    profile_run: Any,
) -> None:
    earlier, truck, van, depot = _fleet(True)
    later, new_truck, new_van, new_depot = _fleet(KeySequence("mig_fleet_ids", batch_size=10))
    profile_run.reset(model_of(earlier), {}, _BINDING)

    with connect(profile_run.port, earlier, binding=_BINDING) as root:
        db = root.using_database_login()
        db.transact(
            lambda tx: [
                tx.insert(truck(id=7, label="hauler", axles=3)),
                tx.insert(van(id=40, label="courier", doors=2)),
                tx.insert(depot(id=93, label="old")),
            ]
        )

        def retire_and_open(tx: TxnContext) -> None:
            # The depot's largest key survives only in a closed history row.
            tx.terminate(tx.find(depot.where(depot.id == 93)).result())
            tx.insert(depot(id=12, label="new"))

        db.transact(retire_and_open)

    _deploy(profile_run, _migration(earlier, later, _BINDING))

    db = own_root(connect(profile_run.port, later, binding=_BINDING)).using_database_login()
    keys = db.transact(
        lambda tx: [
            tx.insert(new_truck(label="tipper", axles=2)).id,
            tx.insert(new_van(label="shuttle", doors=4)).id,
            tx.insert(new_depot(label="annex")).id,
        ]
    )
    assert keys == [94, 95, 96]
    assert _rows(profile_run, "select id from px_eu.mig_vehicle order by id") == [(7,), (94,)]
    assert _rows(profile_run, "select id from px_us.mig_vehicle order by id") == [(40,), (95,)]


def test_a_shrunken_step_starts_the_replacement_root_past_the_earlier_root_s_block(
    profile_run: Any,
) -> None:
    earlier, coupon = _coupons(50)
    later, new_coupon = _coupons(20)
    profile_run.reset(model_of(earlier), {}, _PX)

    with connect(profile_run.port, earlier, binding=_PX) as root:
        # The earlier root reserves 1..50 and stores only its first key.
        assert (
            root.using_database_login().transact(lambda tx: tx.insert(coupon(label="first")).id)
            == 1
        )

    _deploy(profile_run, _migration(earlier, later, _PX))

    db = own_root(connect(profile_run.port, later, binding=_PX)).using_database_login()
    keys = db.transact(lambda tx: [tx.insert(new_coupon(label=f"c{n}")).id for n in range(21)])
    # One block of twenty past the earlier block, then the next block.
    assert keys == list(range(51, 72))
    assert _rows(
        profile_run,
        "select last_value, increment_by from pg_catalog.pg_sequences "
        "where schemaname = 'px' and sequencename = 'mig_coupon_ids'",
    ) == [(71, 20)]
