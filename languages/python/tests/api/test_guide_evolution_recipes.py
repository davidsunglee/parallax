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
    GiftCardPayment,
    adopt,
    changes_since,
    connect_serving,
    edition_of_a_transaction,
    migrate,
    migration_for,
    payments_this_edition_can_read,
)
from parallax.conformance.guide_models import BankTransfer, CardPayment, Customer, Order, Payment
from parallax.core import DomainModel
from parallax.core.entity import model_of
from parallax.core.execution import ServingModel, prepare_model
from parallax.core.metamodel import EntityIdentity
from parallax.core.read_delivery import InvalidDataError
from parallax.descriptor import export_yaml
from parallax.evolution import (
    ConcreteSubtypeAdded,
    ConcreteSubtypeRemoved,
    CoordinatedEvolution,
    CoordinationReason,
    CoordinationRequirement,
    QueryResultMembershipChanged,
    UnilateralEvolution,
)
from parallax.postgres import PostgresAdapter
from parallax.snapshot import Database, TxnContext
from tests._support.db_port import Read, ScriptedAdapter, Transact
from tests._support.root_ownership import own_root

_APRIL_FIRST = dt.date(2024, 4, 1)
_RELEASE_1 = DomainModel(Customer, Order, Payment, CardPayment, BankTransfer)
_RELEASE_2 = DomainModel(Customer, Order, Payment, CardPayment, BankTransfer, GiftCardPayment)
_WITHOUT_BANK_TRANSFERS = DomainModel(Customer, Order, Payment, CardPayment)
_GIFT_CARDS = ConcreteSubtypeAdded(EntityIdentity(None, "GiftCardPayment"))
_ADD_THE_GIFT_CARD_COLUMN = ("alter table payment add column card_number varchar(19)",)


def _release_one_root(profile_run: Any) -> tuple[Database[Any], ServingModel]:
    profile_run.reset(model_of(_RELEASE_1), {})
    adapter = PostgresAdapter(profile_run.connection_info, credentials=profile_run.credentials)
    root, serving = connect_serving(adapter, _RELEASE_1, "release-1")
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

    kept = migrate(export_yaml(_RELEASE_1), _RELEASE_2, _run_on_the_database(profile_run))

    def publish_mid_transaction(tx: TxnContext) -> tuple[str, str]:
        adopt(serving, _RELEASE_2, "release-2")
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
    released = changes_since(kept, _RELEASE_2)
    assert isinstance(released, UnilateralEvolution)
    assert released.operations == ()


def test_an_earlier_edition_sets_aside_rows_a_later_edition_wrote(profile_run: Any) -> None:
    root, serving = _release_one_root(profile_run)
    migrate(export_yaml(_RELEASE_1), _RELEASE_2, _run_on_the_database(profile_run))
    earlier = own_root(
        connect_serving(
            PostgresAdapter(profile_run.connection_info, credentials=profile_run.credentials),
            _RELEASE_1,
            "release-1",
        )[0]
    ).using_database_login()
    adopt(serving, _RELEASE_2, "release-2")
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
        root, serving = connect_serving(cast("PostgresAdapter", adapter), _RELEASE_1, "release-1")
        own_root(root)

        assert edition_of_a_transaction(root.using_database_login()) == "release-1"
        assert serving.current().edition == "release-1"


def test_adding_gift_cards_is_unilateral_and_widens_what_a_payment_query_returns() -> None:
    evolution = changes_since(export_yaml(_RELEASE_1), _RELEASE_2)

    assert isinstance(evolution, UnilateralEvolution)
    assert evolution.operations == (_GIFT_CARDS,)
    assert [(type(impact), impact.scope) for impact in evolution.behavioral_impacts] == [
        (QueryResultMembershipChanged, EntityIdentity(None, "Payment"))
    ]
    assert evolution.overlap_visible_operations == (_GIFT_CARDS,)


def test_retiring_bank_transfers_needs_coordination_and_has_no_migration() -> None:
    retired = ConcreteSubtypeRemoved(EntityIdentity(None, "BankTransfer"))

    evolution = changes_since(export_yaml(_RELEASE_1), _WITHOUT_BANK_TRANSFERS)

    assert isinstance(evolution, CoordinatedEvolution)
    requirement = CoordinationRequirement(
        retired, (CoordinationReason.AUTHORING_SURFACE_CHANGE_REQUIRED,)
    )
    assert evolution.coordination_requirements == (requirement,)
    with pytest.raises(CoordinationRequiredError) as refused:
        migration_for(export_yaml(_RELEASE_1), _WITHOUT_BANK_TRANSFERS)
    assert refused.value.args == ((requirement,),)


def test_a_migration_is_generated_handed_to_the_runner_and_its_descriptor_kept() -> None:
    ran: list[tuple[str, ...]] = []

    kept = migrate(export_yaml(_RELEASE_1), _RELEASE_2, ran.append)

    assert migration_for(export_yaml(_RELEASE_1), _RELEASE_2) == _ADD_THE_GIFT_CARD_COLUMN
    assert ran == [_ADD_THE_GIFT_CARD_COLUMN]
    assert kept == export_yaml(_RELEASE_2)


def test_adopting_a_release_publishes_it_over_the_selection_it_found() -> None:
    serving = ServingModel(prepare_model(_RELEASE_1, edition="release-1"))

    adopt(serving, _RELEASE_2, "release-2")

    assert serving.current().edition == "release-2"
    assert serving.current().model is _RELEASE_2


def test_reading_through_the_overlap_runs_through_the_shipped_surface() -> None:
    with ScriptedAdapter(Read(rows=[_CARD_ROW, _GIFT_CARD_ROW])) as adapter:
        db = own_root(Database.connect(adapter, _RELEASE_1)).using_database_login()

        readable = payments_this_edition_can_read(db, 10)

    assert [(type(payment), payment.id) for payment in readable] == [(CardPayment, 1)]


def test_every_recipe_the_module_exports_has_a_driver() -> None:
    assert sorted(guide_evolution_recipes.__all__) == sorted(
        recipe.__name__
        for recipe in (
            CoordinationRequiredError,
            GiftCardPayment,
            adopt,
            changes_since,
            connect_serving,
            edition_of_a_transaction,
            migrate,
            migration_for,
            payments_this_edition_can_read,
        )
    )
