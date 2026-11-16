"""The Python Guide's model-evolution recipes against real Postgres.

Each recipe's source is a published snippet, so these tests grade the outcome a
reader is told to expect. The database-free run-throughs at the end drive every
recipe body through the shipped surface over a scripted port.
"""

from __future__ import annotations

import contextlib
import datetime as dt
from collections.abc import Mapping
from decimal import Decimal
from typing import Any, cast

import pytest

from parallax.conformance import guide_evolution_recipes
from parallax.conformance.guide_evolution_recipes import (
    CoordinationRequiredError,
    Deployed,
    GiftCardPayment,
    adopt,
    changes_since,
    connect_serving,
    edition_of_a_transaction,
    migrate,
    migration_for,
    migration_steps,
    moves_in,
    payments_this_edition_can_read,
)
from parallax.conformance.guide_models import (
    Address,
    BankTransfer,
    CardPayment,
    Customer,
    Order,
    Payment,
    Shipment,
)
from parallax.core import (
    ONE_TO_MANY,
    Attr,
    DomainModel,
    Entity,
    Int32,
    KeySequence,
    Rel,
    attr,
    index,
    rel,
)
from parallax.core.internal.entity import model_of
from parallax.core.internal.execution import ServingModel, prepare_model
from parallax.core.internal.metamodel import EntityIdentity
from parallax.core.internal.read_delivery import InvalidDataError
from parallax.descriptor import export_yaml
from parallax.evolution import (
    CoordinatedEvolution,
    CoordinationReason,
    CoordinationRequirement,
    UnilateralEvolution,
)
from parallax.evolution.operations import (
    ConcreteSubtypeAdded,
    ConcreteSubtypeRemoved,
    QueryResultMembershipChanged,
    TableRelocated,
)
from parallax.postgres import (
    PostgresAdapter,
    PostgresBinding,
    PostgresEndpoint,
    PostgresLocation,
    PostgresSequence,
    PostgresTable,
)
from parallax.snapshot import Database, TxnContext, connect
from tests._support.bindings import TEST_BINDING
from tests._support.db_port import Read, ScriptedAdapter, Transact
from tests._support.root_ownership import own_root

_APRIL_FIRST = dt.date(2024, 4, 1)
_RELEASE_1 = DomainModel(Customer, Order, Payment, CardPayment, BankTransfer)
_RELEASE_2 = DomainModel(Customer, Order, Payment, CardPayment, BankTransfer, GiftCardPayment)
_WITHOUT_BANK_TRANSFERS = DomainModel(Customer, Order, Payment, CardPayment)
_GIFT_CARDS = ConcreteSubtypeAdded(EntityIdentity(None, "GiftCardPayment"))
_ADD_THE_GIFT_CARD_COLUMN = ("alter table px.payment add column card_number varchar(19)",)
_DEPLOYED_1 = Deployed(export_yaml(_RELEASE_1), TEST_BINDING.to_yaml())


def _release_one_root(profile_run: Any) -> tuple[Database[Any], ServingModel]:
    profile_run.reset(model_of(_RELEASE_1), {}, TEST_BINDING)
    adapter = PostgresAdapter(
        writer=PostgresEndpoint(profile_run.connection_info, credentials=profile_run.credentials)
    )
    root, serving = connect_serving(adapter, _RELEASE_1, TEST_BINDING, "release-1")
    own_root(root)
    root.using_database_login().transact(
        lambda tx: (
            tx.insert(Customer(id=1, name="Ada", email="ada@example.com")),
            tx.insert(
                Order(
                    id=10,
                    customer_id=1,
                    placed_on=_APRIL_FIRST,
                    total=Decimal("125.00"),
                )
            ),
            tx.insert(
                CardPayment(id=1, order_id=10, amount=Decimal("100.00"), card_last_four="4242")
            ),
        )
    )
    return root, serving


def _by_id(payment: Payment) -> int:
    return payment.id


def _run_on_the_database(profile_run: Any) -> Any:
    def run_migration(statements: tuple[str, ...]) -> None:
        with contextlib.closing(profile_run.control()) as control:
            for statement in statements:
                control.execute_write(statement, ())

    return run_migration


def test_a_rollout_migrates_then_publishes_while_an_open_transaction_keeps_its_edition(
    profile_run: Any,
) -> None:
    root, serving = _release_one_root(profile_run)
    db = root.using_database_login()

    kept = migrate(_DEPLOYED_1, _RELEASE_2, TEST_BINDING, _run_on_the_database(profile_run))

    def publish_mid_transaction(tx: TxnContext) -> tuple[str, str]:
        adopt(serving, _RELEASE_2, TEST_BINDING, "release-2")
        standalone = db.find(Payment.where(Payment.order_id == 10))
        return tx.edition, standalone.edition

    assert edition_of_a_transaction(db) == "release-1"
    assert db.transact(publish_mid_transaction) == ("release-1", "release-2")
    assert edition_of_a_transaction(db) == "release-2"

    db.transact(
        lambda tx: tx.insert(
            GiftCardPayment(
                id=2, order_id=10, amount=Decimal("25.00"), card_number="6006491234567890"
            )
        )
    )
    payments = db.find(Payment.where(Payment.order_id == 10)).results()
    assert [(type(payment), payment.id) for payment in sorted(payments, key=_by_id)] == [
        (CardPayment, 1),
        (GiftCardPayment, 2),
    ]
    released = changes_since(kept, _RELEASE_2, TEST_BINDING)
    assert isinstance(released, UnilateralEvolution)
    assert released.operations == ()


def test_an_earlier_edition_sets_aside_rows_a_later_edition_wrote(profile_run: Any) -> None:
    root, serving = _release_one_root(profile_run)
    migrate(_DEPLOYED_1, _RELEASE_2, TEST_BINDING, _run_on_the_database(profile_run))
    earlier = own_root(
        connect_serving(
            PostgresAdapter(
                writer=PostgresEndpoint(
                    profile_run.connection_info, credentials=profile_run.credentials
                )
            ),
            _RELEASE_1,
            TEST_BINDING,
            "release-1",
        )[0]
    ).using_database_login()
    adopt(serving, _RELEASE_2, TEST_BINDING, "release-2")
    root.using_database_login().transact(
        lambda tx: tx.insert(
            GiftCardPayment(
                id=2, order_id=10, amount=Decimal("25.00"), card_number="6006491234567890"
            )
        )
    )

    readable = payments_this_edition_can_read(earlier, 10)

    assert [(type(payment), payment.id) for payment in readable] == [(CardPayment, 1)]
    with pytest.raises(InvalidDataError) as refused:
        earlier.find(Payment.where(Payment.order_id == 10)).results()
    assert refused.value.edition == "release-1"
    assert [record.ordinal for record in refused.value.invalid_data] == [1]


_WITH_SHIPMENTS = DomainModel(Customer, Order, Payment, CardPayment, BankTransfer, Shipment)
_SHIPMENTS_APART = PostgresBinding(
    default=PostgresLocation(schema="px"),
    entities={"Shipment": PostgresTable(schema="px_fulfillment")},
)


def test_a_release_placing_a_new_entity_in_a_new_schema_migrates_then_publishes(
    profile_run: Any,
) -> None:
    # The deployment owns schemas: `px_fulfillment` exists, empty and ungranted,
    # before the migration creates the release's table in it.
    profile_run.reset(model_of(_WITH_SHIPMENTS), {}, _SHIPMENTS_APART)
    root, serving = _release_one_root(profile_run)

    def run_and_grant(statements: tuple[str, ...]) -> None:
        _run_on_the_database(profile_run)(
            (
                *statements,
                f'grant usage on schema px_fulfillment to "{profile_run.default_role.name}"',
                "grant select, insert, update, delete on all tables in schema px_fulfillment "
                f'to "{profile_run.default_role.name}"',
            )
        )

    kept = migrate(_DEPLOYED_1, _WITH_SHIPMENTS, _SHIPMENTS_APART, run_and_grant)
    adopt(serving, _WITH_SHIPMENTS, _SHIPMENTS_APART, "release-3")
    root.using_database_login().transact(
        lambda tx: tx.insert(
            Shipment(
                id=1, order_id=10, ship_to=Address(street="1 Main St", city="Leeds", postcode="LS1")
            )
        )
    )

    with contextlib.closing(profile_run.control()) as control:
        assert control.execute("select id, order_id from px_fulfillment.shipment", ()) == [(1, 10)]
    assert PostgresBinding.from_yaml(kept.binding) == _SHIPMENTS_APART
    assert changes_since(kept, _WITH_SHIPMENTS, _SHIPMENTS_APART).operations == ()


def test_a_release_that_moves_a_table_reports_the_move_and_has_no_migration() -> None:
    moved = PostgresBinding(
        default=PostgresLocation(schema="px"),
        entities={"Order": PostgresTable(schema="px_sales")},
    )

    evolution = changes_since(_DEPLOYED_1, _RELEASE_2, moved)

    assert isinstance(evolution, CoordinatedEvolution)
    assert moves_in(evolution) == ["Order: px.orders -> px_sales.orders"]
    with pytest.raises(CoordinationRequiredError) as refused:
        migration_for(_DEPLOYED_1, _RELEASE_2, moved)
    ((requirement,),) = refused.value.args
    assert isinstance(requirement.operation, TableRelocated)
    assert requirement.reasons == (CoordinationReason.DATABASE_MIGRATION_REQUIRED,)


class Ticket(Entity, table="ticket"):
    id: Attr[int] = attr(primary_key=KeySequence(name="tickets"))


def test_a_sequence_move_is_reported_from_where_to_where() -> None:
    tickets = DomainModel(Ticket)
    keys_apart = PostgresBinding(
        default=PostgresLocation(schema="px"),
        sequences={"tickets": PostgresSequence(schema="px_keys", name="ticket_numbers")},
    )

    evolution = changes_since(
        Deployed(export_yaml(tickets), TEST_BINDING.to_yaml()), tickets, keys_apart
    )

    assert moves_in(evolution) == ["sequence tickets: px.tickets -> px_keys.ticket_numbers"]


_CARD_ROW: Mapping[str, object] = {
    "id": 1,
    "order_id": 10,
    "amount": Decimal("100.00"),
    "kind": "card",
    "card_last_four": "4242",
    "reference": None,
}
_GIFT_CARD_ROW: Mapping[str, object] = {
    "id": 2,
    "order_id": 10,
    "amount": Decimal("25.00"),
    "kind": "gift-card",
    "card_last_four": None,
    "reference": None,
}


def test_serving_an_edition_runs_through_the_shipped_surface() -> None:
    with ScriptedAdapter(Transact()) as adapter:
        root, serving = connect_serving(
            cast("PostgresAdapter", adapter), _RELEASE_1, TEST_BINDING, "release-1"
        )
        own_root(root)

        assert edition_of_a_transaction(root.using_database_login()) == "release-1"
        assert serving.current().edition == "release-1"


def test_adding_gift_cards_is_unilateral_and_widens_what_a_payment_query_returns() -> None:
    evolution = changes_since(_DEPLOYED_1, _RELEASE_2, TEST_BINDING)

    assert isinstance(evolution, UnilateralEvolution)
    assert evolution.operations == (_GIFT_CARDS,)
    assert [(type(impact), impact.scope) for impact in evolution.behavioral_impacts] == [
        (QueryResultMembershipChanged, EntityIdentity(None, "Payment"))
    ]
    assert evolution.overlap_visible_operations == (_GIFT_CARDS,)


def test_retiring_bank_transfers_needs_coordination_and_has_no_migration() -> None:
    retired = ConcreteSubtypeRemoved(EntityIdentity(None, "BankTransfer"))

    evolution = changes_since(_DEPLOYED_1, _WITHOUT_BANK_TRANSFERS, TEST_BINDING)

    assert isinstance(evolution, CoordinatedEvolution)
    requirement = CoordinationRequirement(
        retired, (CoordinationReason.AUTHORING_SURFACE_CHANGE_REQUIRED,)
    )
    assert evolution.coordination_requirements == (requirement,)
    with pytest.raises(CoordinationRequiredError) as refused:
        migration_for(_DEPLOYED_1, _WITHOUT_BANK_TRANSFERS, TEST_BINDING)
    assert refused.value.args == ((requirement,),)


def test_a_migration_is_generated_handed_to_the_runner_and_its_descriptor_kept() -> None:
    ran: list[tuple[str, ...]] = []

    kept = migrate(_DEPLOYED_1, _RELEASE_2, TEST_BINDING, ran.append)

    assert migration_for(_DEPLOYED_1, _RELEASE_2, TEST_BINDING) == _ADD_THE_GIFT_CARD_COLUMN
    assert ran == [_ADD_THE_GIFT_CARD_COLUMN]
    assert kept == Deployed(export_yaml(_RELEASE_2), TEST_BINDING.to_yaml())


def test_adopting_a_release_publishes_it_over_the_selection_it_found() -> None:
    serving = ServingModel(prepare_model(_RELEASE_1, edition="release-1", binding=TEST_BINDING))

    adopt(serving, _RELEASE_2, TEST_BINDING, "release-2")

    assert serving.current().edition == "release-2"
    assert serving.current().model is _RELEASE_2


def test_reading_through_the_overlap_runs_through_the_shipped_surface() -> None:
    with ScriptedAdapter(Read(rows=[_CARD_ROW, _GIFT_CARD_ROW])) as adapter:
        db = own_root(
            Database.connect(adapter, _RELEASE_1, binding=TEST_BINDING)
        ).using_database_login()

        readable = payments_this_edition_can_read(db, 10)

    assert [(type(payment), payment.id) for payment in readable] == [(CardPayment, 1)]


def _customers_with_generated_keys() -> tuple[DomainModel, type[Entity]]:
    """The shop's customers and orders, with the release's one change: each
    customer's key comes from the ``customer_ids`` allocator; and that release's
    customer class."""

    class Customer(Entity, table="customer"):
        id: Attr[int] = attr(primary_key=KeySequence("customer_ids"))
        name: Attr[str] = attr(max_length=100)
        email: Attr[str | None] = attr(max_length=200)
        orders: Rel[tuple[Order, ...]] = rel(cardinality=ONE_TO_MANY, join=("id", "customer_id"))

    class Order(Entity, table="orders", indices=(index("orders_customer", "customer_id"),)):
        id: Attr[int] = attr(primary_key=True)
        customer_id: Attr[int]
        placed_on: Attr[dt.date]
        total: Attr[Decimal] = attr(precision=12, scale=2)
        version: Attr[int] = attr(type=Int32, optimistic_locking=True)
        customer: Rel[Customer | None] = rel(reverse_of="orders")

    return DomainModel(Customer, Order), Customer


_SHOP_SCHEMA = PostgresBinding(default=PostgresLocation(schema="shop"))
_ASSIGNED_CUSTOMERS = DomainModel(Customer, Order)


def test_moving_customers_to_generated_keys_drains_then_creates_and_positions_their_sequence() -> (
    None
):
    steps = migration_steps(
        Deployed(export_yaml(_ASSIGNED_CUSTOMERS), _SHOP_SCHEMA.to_yaml()),
        _customers_with_generated_keys()[0],
        _SHOP_SCHEMA,
    )

    assert steps == [
        "-- DRAIN_EARLIER_ROOTS",
        "create sequence shop.customer_ids as bigint increment by 100"
        " minvalue -9223372036854775808 maxvalue 9223372036854775807 start with 1 no cycle",
        "select case when t0.next_key > 9223372036854775807"
        " then pg_catalog.setval('shop.customer_ids', 9223372036854775807, true)"
        " else pg_catalog.setval('shop.customer_ids', cast(t0.next_key as bigint), false) end"
        " from (select greatest((select case when t1.is_called"
        " then cast(t1.last_value as numeric) + 100 else t1.last_value end"
        " from shop.customer_ids t1),"
        " (select cast(max(t2.id) as numeric) + 1 from shop.customer t2)) next_key) t0",
    ]


def test_a_unilateral_release_s_steps_are_its_schema_delta() -> None:
    assert migration_steps(_DEPLOYED_1, _RELEASE_2, TEST_BINDING) == list(_ADD_THE_GIFT_CARD_COLUMN)


def test_customers_moved_to_generated_keys_take_keys_past_every_stored_one(
    profile_run: Any,
) -> None:
    profile_run.reset(model_of(_ASSIGNED_CUSTOMERS), {}, TEST_BINDING)
    with connect(profile_run.port, _ASSIGNED_CUSTOMERS, binding=TEST_BINDING) as earlier:
        earlier.using_database_login().transact(
            lambda tx: (
                tx.insert(Customer(id=41, name="Ada", email=None)),
                tx.insert(Customer(id=7, name="Grace", email=None)),
            )
        )
    release, released_customer = _customers_with_generated_keys()
    steps = migration_steps(
        Deployed(export_yaml(_ASSIGNED_CUSTOMERS), TEST_BINDING.to_yaml()), release, TEST_BINDING
    )
    assert steps[0] == "-- DRAIN_EARLIER_ROOTS"
    role = profile_run.default_role.name
    with contextlib.closing(profile_run.control()) as control:
        for statement in steps[1:]:
            control.execute_write(statement, ())
        control.execute_write(f'grant usage on sequence px.customer_ids to "{role}"', ())

    db = own_root(connect(profile_run.port, release, binding=TEST_BINDING)).using_database_login()
    new_customer = cast("Any", released_customer)
    key = db.transact(lambda tx: tx.insert(new_customer(name="Edsger", email=None)).id)

    assert key == 42


def test_every_recipe_the_module_exports_has_a_driver() -> None:
    assert sorted(guide_evolution_recipes.__all__) == sorted(
        recipe.__name__
        for recipe in (
            CoordinationRequiredError,
            Deployed,
            GiftCardPayment,
            adopt,
            changes_since,
            connect_serving,
            edition_of_a_transaction,
            migrate,
            migration_for,
            migration_steps,
            moves_in,
            payments_this_edition_can_read,
        )
    )
