"""The README's and the Python Guide's teaching recipes against real Postgres.

Each recipe's source is a published snippet, so these tests grade the outcome a
reader is told to expect. The database-free run-through at the end drives every
recipe body through the shipped surface over a scripted port.
"""

from __future__ import annotations

import ast
import builtins
import contextlib
import datetime as dt
from collections.abc import Callable, Mapping, Sequence
from decimal import Decimal
from typing import Any, cast

import pytest

from parallax.conformance import guide_recipes
from parallax.conformance.guide_models import (
    SHOP_MODEL,
    Address,
    BankTransfer,
    CardPayment,
    CreditLimit,
    Customer,
    Order,
    Payment,
    Price,
    Product,
    Shipment,
)
from parallax.conformance.guide_recipes import (
    add_and_find_a_customer,
    configure_the_database,
    credit_limit_on_record,
    customers_with_an_order_over,
    customers_with_an_order_over_as_wire,
    payments_for,
    place_an_order,
    products_named,
    run_a_summer_sale,
    shipments_to,
    table_statements,
)
from parallax.conformance.scripted_clock import ScriptedClock
from parallax.conformance.usage_guide import snippet_sources
from parallax.core import DomainModel
from parallax.core.base import INFINITY
from parallax.core.db_port import Bind, Committed, DatabaseConnection, Row, TransactionOutcome
from parallax.core.dialect import POSTGRES, Dialect
from parallax.core.entity import model_of
from parallax.postgres import PostgresAdapter
from parallax.snapshot import Database, ScopedDatabase, WireEntity, connect
from tests._support.db_port import ConnectsAsItself, projected_row
from tests._support.root_ownership import own_root

_JAN = dt.datetime(2024, 1, 1, tzinfo=dt.UTC)
_MAR = dt.datetime(2024, 3, 1, tzinfo=dt.UTC)
_JUN = dt.datetime(2024, 6, 1, tzinfo=dt.UTC)
_JUL = dt.datetime(2024, 7, 1, tzinfo=dt.UTC)
_SEP = dt.datetime(2024, 9, 1, tzinfo=dt.UTC)
_OCT = dt.datetime(2024, 10, 1, tzinfo=dt.UTC)


def _shop(profile_run: Any, **connect_options: Any) -> ScopedDatabase:
    profile_run.reset(model_of(SHOP_MODEL), {})
    return own_root(connect(profile_run.port, SHOP_MODEL, **connect_options)).using_database_login()


def _seed_customers(db: ScopedDatabase) -> None:
    db.transact(
        lambda tx: (
            tx.insert(Customer(id=1, name="Ada", email="ada@example.com")),
            tx.insert(Customer(id=2, name="Grace", email=None)),
            tx.insert(
                Order(id=10, customer_id=1, placed_on=dt.date(2024, 4, 1), total=Decimal("150.00"))
            ),
            tx.insert(
                Order(id=11, customer_id=1, placed_on=dt.date(2024, 4, 9), total=Decimal("20.00"))
            ),
            tx.insert(
                Order(id=12, customer_id=2, placed_on=dt.date(2024, 4, 3), total=Decimal("40.00"))
            ),
        )
    )


def test_the_generated_statements_create_tables_the_first_program_runs_against(
    profile_run: Any,
) -> None:
    # The provisioned schema grants the test login's role its table privileges;
    # replacing the tables with the recipe's own statements, as a migration
    # would, leaves that grant to restate.
    model = DomainModel(Customer, Order)
    profile_run.reset(model_of(model), {})
    with contextlib.closing(profile_run.control()) as control:
        control.execute_write("drop table customer, orders", ())
        for statement in table_statements(model):
            control.execute_write(statement, ())
        control.execute_write(
            "grant select, insert, update, delete on all tables in schema public "
            f'to "{profile_run.default_role.name}"',
            (),
        )

    adapter = configure_the_database(profile_run.connection_info, profile_run.credentials.secret)
    customer = add_and_find_a_customer(adapter)

    assert type(customer) is Customer
    assert (customer.id, customer.name, customer.email) == (1, "Ada Lovelace", "ada@example.com")


def test_a_relationship_filter_returns_matching_customers_with_every_order(
    profile_run: Any,
) -> None:
    db = _shop(profile_run)
    _seed_customers(db)

    customers = customers_with_an_order_over(db, Decimal("100.00"))

    assert [customer.name for customer in customers] == ["Ada"]
    # The filter selects customers; the include still loads each one's whole
    # relationship, the small order beside the qualifying one included.
    assert sorted(order.id for order in customers[0].orders) == [10, 11]


def test_the_wire_read_answers_the_typed_reads_values_as_mappings(profile_run: Any) -> None:
    db = _shop(profile_run)
    _seed_customers(db)

    (customer,) = customers_with_an_order_over_as_wire(db, Decimal("100.00"))

    assert {key: customer[key] for key in ("id", "name", "email")} == {
        "id": 1,
        "name": "Ada",
        "email": "ada@example.com",
    }
    orders = cast("Sequence[WireEntity]", customer["orders"])
    assert sorted((order["id"], order["total"]) for order in orders) == [
        (10, "150.00"),
        (11, "20.00"),
    ]


def test_an_order_and_its_customers_change_commit_together(profile_run: Any) -> None:
    db = _shop(profile_run)
    _seed_customers(db)

    place_an_order(db)

    customer = db.find(Customer.where(Customer.id == 1).include(Customer.orders)).result()
    assert customer.email == "ada@example.org"
    assert sorted(order.id for order in customer.orders) == [7, 10, 11]
    placed = next(order for order in customer.orders if order.id == 7)
    assert (placed.total, placed.version) == (Decimal("80.00"), 1)


def test_an_as_of_read_answers_the_limit_recorded_then(profile_run: Any) -> None:
    db = _shop(profile_run, clock=ScriptedClock([_JAN, _MAR]))
    db.transact(lambda tx: tx.insert(CreditLimit(customer_id=1, amount=Decimal("1000.00"))))

    def raise_the_limit(tx: Any) -> None:
        limit = tx.find(CreditLimit.where(CreditLimit.customer_id == 1)).result()
        tx.amend(limit.edit(amount=Decimal("2500.00")))

    db.transact(raise_the_limit)

    assert credit_limit_on_record(db, 1, dt.datetime(2024, 2, 1, tzinfo=dt.UTC)) == Decimal(
        "1000.00"
    )
    assert credit_limit_on_record(db, 1, dt.datetime(2024, 4, 1, tzinfo=dt.UTC)) == Decimal(
        "2500.00"
    )


def test_a_bounded_amendment_changes_only_its_window(profile_run: Any) -> None:
    db = _shop(profile_run)
    db.transact(lambda tx: tx.insert(Price(sku="TEA-1", amount=Decimal("10.00")), valid_from=_JAN))

    run_a_summer_sale(db)

    def price_on(day: dt.datetime) -> Decimal:
        query = Price.where(Price.sku == "TEA-1").as_of(valid_time=day)
        return db.find(query).result().amount

    assert price_on(_MAR) == Decimal("10.00")
    assert price_on(_JUN) == Decimal("8.00")
    assert price_on(_JUL) == Decimal("8.00")
    assert price_on(_SEP) == Decimal("10.00")
    assert price_on(_OCT) == Decimal("10.00")


def test_a_value_object_field_filters_like_a_column(profile_run: Any) -> None:
    db = _shop(profile_run)
    db.transact(
        lambda tx: (
            tx.insert(
                Shipment(
                    id=1,
                    order_id=10,
                    ship_to=Address(street="1 Fjord Vei", city="Bergen", postcode="5003"),
                    tracking_number=None,
                )
            ),
            tx.insert(
                Shipment(
                    id=2,
                    order_id=11,
                    ship_to=Address(street="2 Karl Johans gate", city="Oslo", postcode="0154"),
                    tracking_number="TRK-2",
                )
            ),
        )
    )

    (shipment,) = shipments_to(db, "Oslo")

    assert shipment.id == 2
    assert shipment.ship_to == Address(street="2 Karl Johans gate", city="Oslo", postcode="0154")


def test_a_family_read_materializes_each_concrete_class(profile_run: Any) -> None:
    db = _shop(profile_run)
    db.transact(
        lambda tx: (
            tx.insert(
                CardPayment(id=1, order_id=10, amount=Decimal("100.00"), card_last_four="4242")
            ),
            tx.insert(BankTransfer(id=2, order_id=10, amount=Decimal("50.00"), reference="INV-10")),
            tx.insert(
                CardPayment(id=3, order_id=11, amount=Decimal("20.00"), card_last_four="1111")
            ),
        )
    )

    by_id = {payment.id: payment for payment in payments_for(db, 10)}

    assert sorted(by_id) == [1, 2]
    assert type(by_id[1]) is CardPayment
    assert type(by_id[2]) is BankTransfer
    assert by_id[1].card_last_four == "4242"
    assert by_id[2].reference == "INV-10"


def test_a_document_layout_entity_reads_like_a_column_one(profile_run: Any) -> None:
    db = _shop(profile_run)
    db.transact(
        lambda tx: (
            tx.insert(Product(sku="TEA-1", name="Green tea", description="Sencha, 100 g")),
            tx.insert(Product(sku="TEA-2", name="Black tea", description=None)),
        )
    )

    (product,) = products_named(db, "Green tea")

    assert (product.sku, product.description) == ("TEA-1", "Sencha, 100 g")
    # Every declared member lives in one JSON document column beside the key.
    with contextlib.closing(profile_run.control()) as control:
        columns = control.execute(
            "select column_name from information_schema.columns "
            "where table_name = 'product' order by column_name",
            (),
        )
    assert [row[0] for row in columns] == ["payload", "sku"]


# --------------------------------------------------------------------------- #
# Database-free run-through of every recipe body.                              #
# --------------------------------------------------------------------------- #
class _ScriptedPort(ConnectsAsItself):
    """A fake `m-db-port` answering successive reads with scripted rows, then
    none, every write with one affected row, and every boundary by committing."""

    dialect: Dialect = POSTGRES

    def __init__(self, *reads: Sequence[Mapping[str, object]]) -> None:
        self.reads = list(reads)

    def execute(
        self, sql: str, binds: Sequence[Bind], document_reads: Sequence[tuple[int, int]] = ()
    ) -> list[Row]:
        answered = self.reads.pop(0) if self.reads else ()
        return [projected_row(sql, row) for row in answered]

    def execute_write(self, sql: str, binds: Sequence[Bind]) -> int:
        return 1

    def transaction[T](
        self,
        body: Callable[[DatabaseConnection], T],
        *,
        isolation: str | None = None,
        access_mode: str | None = None,
    ) -> TransactionOutcome[T]:
        return Committed(body(cast("DatabaseConnection", self)))


_CUSTOMER_ROW: Mapping[str, object] = {"id": 1, "name": "Ada", "email": "ada@example.com"}
_ORDER_ROW: Mapping[str, object] = {
    "id": 10,
    "customer_id": 1,
    "placed_on": dt.date(2024, 4, 1),
    "total": Decimal("150.00"),
    "version": 1,
}
_CREDIT_LIMIT_ROW: Mapping[str, object] = {
    "customer_id": 1,
    "amount": Decimal("1000.00"),
    "in_z": _JAN,
    "out_z": INFINITY,
}
_PRICE_ROW: Mapping[str, object] = {
    "sku": "TEA-1",
    "amount": Decimal("10.00"),
    "from_z": _JAN,
    "thru_z": INFINITY,
    "in_z": _JAN,
    "out_z": INFINITY,
}


def test_the_first_program_runs_through_the_shipped_surface() -> None:
    model = DomainModel(Customer, Order)
    statements = table_statements(model)
    assert [statement.split(" (")[0] for statement in statements] == [
        "create table customer",
        "create table orders",
        "create index pxi_orders_order_orders_custom_b818642dd60617fc200f3b8e1a175ccb on orders",
    ]

    adapter = configure_the_database("postgresql://shop@localhost/shop", "s3cret")
    assert type(adapter) is PostgresAdapter

    customer = add_and_find_a_customer(cast("PostgresAdapter", _ScriptedPort([_CUSTOMER_ROW])))
    assert customer.name == "Ada"


def _over_one_hundred(db: ScopedDatabase) -> Any:
    return customers_with_an_order_over(db, Decimal("100.00"))


def _over_one_hundred_as_wire(db: ScopedDatabase) -> Any:
    return customers_with_an_order_over_as_wire(db, Decimal("100.00"))


def _limit_on_the_first_of_february(db: ScopedDatabase) -> Decimal:
    return credit_limit_on_record(db, 1, dt.datetime(2024, 2, 1, tzinfo=dt.UTC))


def _shipments_to_oslo(db: ScopedDatabase) -> list[Shipment]:
    return shipments_to(db, "Oslo")


def _payments_for_order_ten(db: ScopedDatabase) -> list[Payment]:
    return payments_for(db, 10)


def _products_named_green_tea(db: ScopedDatabase) -> list[Product]:
    return products_named(db, "Green tea")


@pytest.mark.parametrize(
    ("recipe", "reads"),
    [
        pytest.param(_over_one_hundred, ([_CUSTOMER_ROW], [_ORDER_ROW]), id="relationship-filter"),
        pytest.param(_over_one_hundred_as_wire, ([_CUSTOMER_ROW], [_ORDER_ROW]), id="wire-read"),
        pytest.param(place_an_order, ([_CUSTOMER_ROW],), id="insert-and-amend"),
        pytest.param(_limit_on_the_first_of_february, ([_CREDIT_LIMIT_ROW],), id="as-of-read"),
        pytest.param(run_a_summer_sale, ([_PRICE_ROW], [_PRICE_ROW]), id="bounded-amendment"),
        pytest.param(_shipments_to_oslo, (), id="value-object-filter"),
        pytest.param(_payments_for_order_ten, (), id="family-read"),
        pytest.param(_products_named_green_tea, (), id="document-layout-read"),
    ],
)
def test_every_recipe_runs_through_the_shipped_surface(
    recipe: Callable[[ScopedDatabase], object], reads: tuple[Sequence[Mapping[str, object]], ...]
) -> None:
    recipe(own_root(Database.connect(_ScriptedPort(*reads), SHOP_MODEL)).using_database_login())


def test_every_recipe_the_module_exports_has_a_driver() -> None:
    assert sorted(guide_recipes.__all__) == sorted(
        recipe.__name__
        for recipe in (
            add_and_find_a_customer,
            configure_the_database,
            credit_limit_on_record,
            customers_with_an_order_over,
            customers_with_an_order_over_as_wire,
            payments_for,
            place_an_order,
            products_named,
            run_a_summer_sale,
            shipments_to,
            table_statements,
        )
    )


def _bound_and_loaded(source: str) -> tuple[set[str], set[str]]:
    """Every name ``source`` binds and every name it reads, scope-blind."""
    bound: set[str] = set()
    loaded: set[str] = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.alias):
            bound.add((node.asname or node.name).split(".")[0])
        elif isinstance(node, ast.FunctionDef | ast.ClassDef):
            bound.add(node.name)
        elif isinstance(node, ast.arg):
            bound.add(node.arg)
        elif isinstance(node, ast.Name):
            (bound if isinstance(node.ctx, ast.Store) else loaded).add(node.id)
    return bound, loaded


def test_the_getting_started_imports_bind_every_name_its_snippets_read() -> None:
    # Getting started is the one page a reader copies whole, so its import block
    # has to resolve and has to cover every name the snippets after it use.
    sources = snippet_sources()
    imports = sources["getting-started-imports"]
    exec(compile(imports, "getting-started-imports", "exec"), {})
    shown = "\n\n".join(
        sources[source_id]
        for source_id in (
            "getting-started-imports",
            "declare-customers-and-orders",
            "create-tables-from-the-model",
            "connect-and-run-a-first-transaction",
        )
    )
    bound, loaded = _bound_and_loaded(shown)

    assert loaded - bound - set(dir(builtins)) == set()
