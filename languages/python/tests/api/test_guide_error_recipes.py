"""The Python Guide's Errors and Operations recipes against real Postgres.

Each recipe's source is a published snippet, so these tests grade the outcome a
reader is told to expect, reading database failures through public attributes
only. The database-free run-throughs at the end drive every recipe body through
the shipped surface over a scripted port.
"""

from __future__ import annotations

import contextlib
import datetime as dt
import logging
from collections.abc import Callable, Mapping
from decimal import Decimal
from typing import Any

import pytest

from parallax.conformance import case_format, guide_error_recipes
from parallax.conformance.graph_models import POLICY_MODEL
from parallax.conformance.guide_error_recipes import (
    add_a_customer_unless_the_id_is_taken,
    add_a_shipment_unless_its_tracking_number_is_taken,
    change_a_customer_from_a_form,
    created_index_name,
    find_with_a_client_query,
    http_status_for,
    open_the_shop_database,
    price_a_window_unless_it_is_priced,
    problems_in_a_model,
    run_or_retry_later,
)
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
from parallax.conformance.guide_recipes import Delivery
from parallax.conformance.scripted_clock import ScriptedClock
from parallax.core import (
    ConflictError,
    ConnectionAcquisitionError,
    EditError,
    InternalError,
    NoResultFound,
    ParallaxError,
    UnsupportedError,
    UsageError,
    WritePreconditionError,
)
from parallax.core.base import INFINITY
from parallax.core.db_error import Category, DatabaseError, PhysicalIndexName
from parallax.core.db_port import Password
from parallax.core.dialect import POSTGRES
from parallax.core.entity import model_of
from parallax.core.execution import RetryPolicy
from parallax.evolution import ABSENT, SchemaDelta, evolve, schema_delta
from parallax.postgres import PostgresAdapter
from parallax.snapshot import Database, ScopedDatabase, TxnContext, connect
from tests._support.db_port import Read, RefusingAdapter, ScriptedAdapter, Transact, Write
from tests._support.root_ownership import own_root


def _shop(profile_run: Any) -> ScopedDatabase:
    profile_run.reset(model_of(SHOP_MODEL), {})
    db = own_root(connect(profile_run.port, SHOP_MODEL)).using_database_login()
    db.transact(lambda tx: tx.insert(Customer(id=1, name="Ada", email="ada@example.com")))
    return db


def _customer(db: ScopedDatabase, customer_id: int) -> Customer | None:
    return db.find(Customer.where(Customer.id == customer_id)).result_or_none()


def _rollout() -> SchemaDelta:
    """The delta that provisions the shop model, as the database under test was."""
    return schema_delta(evolve(ABSENT, SHOP_MODEL), POSTGRES)


def _tracking_index() -> PhysicalIndexName:
    return created_index_name(_rollout(), "Shipment", "shipment_tracking_number")


_HOME = Address(street="1 Main St", city="Leeds", postcode="LS1 1AA")


def _shipment(shipment_id: int, tracking_number: str | None) -> Shipment:
    return Shipment(id=shipment_id, order_id=10, ship_to=_HOME, tracking_number=tracking_number)


def _shipped(profile_run: Any) -> ScopedDatabase:
    db = _shop(profile_run)
    db.transact(lambda tx: tx.insert(_shipment(1, "TRK-1")))
    return db


def _shipments(db: ScopedDatabase) -> list[Shipment]:
    return db.find(Shipment.where(Shipment.all).order_by(Shipment.id.asc())).results()


def test_a_model_missing_a_relationships_entity_reports_the_reference() -> None:
    assert problems_in_a_model(Order) == [
        "metamodel-unresolved-entity-reference: no declaration resolves to Entity 'Customer'"
    ]


def test_the_whole_shop_model_reports_no_problems() -> None:
    accepted = problems_in_a_model(
        Customer, Order, Shipment, Payment, CardPayment, BankTransfer, CreditLimit, Price, Product
    )

    assert accepted == []


def test_a_form_reports_every_refused_field_by_member_and_amends_nothing(
    profile_run: Any,
) -> None:
    db = _shop(profile_run)

    refused = change_a_customer_from_a_form(db, 1, {"name": None, "email": 5})

    assert sorted(refused, key=str) == ["email", "name"]
    assert all(refused.values())
    assert _customer(db, 1) == Customer(id=1, name="Ada", email="ada@example.com")


def test_a_valid_form_amends_the_customer_and_reports_nothing(profile_run: Any) -> None:
    db = _shop(profile_run)

    refused = change_a_customer_from_a_form(db, 1, {"email": "ada@example.org"})

    assert refused == {}
    assert _customer(db, 1) == Customer(id=1, name="Ada", email="ada@example.org")


def test_a_duplicate_key_surfaces_as_a_unique_violation_through_public_attributes(
    profile_run: Any,
) -> None:
    db = _shop(profile_run)

    with pytest.raises(DatabaseError) as failed:
        db.transact(lambda tx: tx.insert(Customer(id=1, name="Grace", email=None)))

    cause = failed.value
    assert (cause.category, cause.native_code, cause.violated_index) == (
        "uniqueViolation",
        "23505",
        PhysicalIndexName("customer_pkey"),
    )


def test_a_taken_id_answers_false_and_leaves_the_existing_customer(profile_run: Any) -> None:
    db = _shop(profile_run)

    added = add_a_customer_unless_the_id_is_taken(db, Customer(id=1, name="Grace", email=None))

    assert added is False
    assert _customer(db, 1) == Customer(id=1, name="Ada", email="ada@example.com")


def test_a_free_id_is_added(profile_run: Any) -> None:
    db = _shop(profile_run)

    added = add_a_customer_unless_the_id_is_taken(db, Customer(id=3, name="Grace", email=None))

    assert added is True
    assert _customer(db, 3) == Customer(id=3, name="Grace", email=None)


_MAR, _JUN, _SEP, _DEC = (dt.datetime(2024, month, 1, tzinfo=dt.UTC) for month in (3, 6, 9, 12))


def _prices(profile_run: Any) -> list[tuple[object, ...]]:
    return [
        tuple(row)
        for row in profile_run.port.execute(
            "select amount, from_z, thru_z, in_z, out_z from price order by in_z, from_z", []
        )
    ]


@pytest.mark.parametrize(
    ("start", "end"), [(_JUN, _DEC), (_MAR, _SEP)], ids=["partly-priced", "same-end"]
)
def test_a_priced_window_answers_false_at_once_and_keeps_the_stored_price(
    profile_run: Any, start: dt.datetime, end: dt.datetime
) -> None:
    db = _shop(profile_run)
    db.transact(
        lambda tx: tx.insert(
            Price(sku="TEA-1", amount=Decimal("4.00")), valid_from=_MAR, until=_SEP
        )
    )
    before = _prices(profile_run)

    priced = price_a_window_unless_it_is_priced(
        db, Price(sku="TEA-1", amount=Decimal("5.00")), start, end
    )

    assert priced is False
    assert _prices(profile_run) == before


def test_an_unpriced_window_is_priced(profile_run: Any) -> None:
    db = _shop(profile_run)
    db.transact(
        lambda tx: tx.insert(
            Price(sku="TEA-1", amount=Decimal("4.00")), valid_from=_MAR, until=_SEP
        )
    )

    priced = price_a_window_unless_it_is_priced(
        db, Price(sku="TEA-1", amount=Decimal("5.00")), _SEP, _DEC
    )

    assert priced is True
    assert [row[0] for row in _prices(profile_run)] == [Decimal("4.00"), Decimal("5.00")]


def test_a_window_priced_only_in_terminated_history_is_priced_past_a_lagging_clock(
    profile_run: Any,
) -> None:
    # Known from January until its termination in May, the price is no longer
    # current. A clock at April overlaps that history, so storage refuses the
    # first attempt; the retry prices the window in June.
    jan, apr, may = (dt.datetime(2024, month, 1, tzinfo=dt.UTC) for month in (1, 4, 5))
    profile_run.reset(model_of(SHOP_MODEL), {})
    seeded = own_root(
        connect(profile_run.port, SHOP_MODEL, clock=ScriptedClock([jan, may]))
    ).using_database_login()
    seeded.transact(
        lambda tx: tx.insert(
            Price(sku="TEA-1", amount=Decimal("4.00")), valid_from=_MAR, until=_SEP
        )
    )

    def terminate(tx: TxnContext) -> None:
        tx.terminate(tx.find(Price.where(Price.sku == "TEA-1").as_of(valid_time=_MAR)).result())

    seeded.transact(terminate)
    lagging = own_root(
        connect(profile_run.port, SHOP_MODEL, clock=ScriptedClock([apr, _JUN]))
    ).using_database_login()

    priced = price_a_window_unless_it_is_priced(
        lagging, Price(sku="TEA-1", amount=Decimal("5.00")), _JUN, _DEC
    )

    assert priced is True
    assert _prices(profile_run) == [
        (Decimal("4.00"), _MAR, _SEP, jan, may),
        (Decimal("5.00"), _JUN, _DEC, _JUN, INFINITY),
    ]


def test_an_uncategorized_database_failure_passes_through(profile_run: Any) -> None:
    db = _shop(profile_run)
    with contextlib.closing(profile_run.control()) as control:
        control.execute_write("drop table customer", ())

    with pytest.raises(DatabaseError) as failed:
        add_a_customer_unless_the_id_is_taken(db, Customer(id=3, name="Grace", email=None))

    cause = failed.value
    assert (cause.category, cause.native_code, cause.violated_index) == (None, "42P01", None)


def test_the_rollout_names_the_tracking_number_index_it_created() -> None:
    (created,) = [index for index in _rollout().created_indices if index.unique]

    assert _tracking_index() == created.physical_index_name
    assert created.physical_table.name == "shipment"


def test_a_taken_tracking_number_answers_false_and_adds_nothing(profile_run: Any) -> None:
    db = _shipped(profile_run)

    added = add_a_shipment_unless_its_tracking_number_is_taken(
        db, _shipment(2, "TRK-1"), _tracking_index()
    )

    assert added is False
    assert _shipments(db) == [_shipment(1, "TRK-1")]


def test_a_free_tracking_number_is_added(profile_run: Any) -> None:
    db = _shipped(profile_run)

    added = add_a_shipment_unless_its_tracking_number_is_taken(
        db, _shipment(2, "TRK-2"), _tracking_index()
    )

    assert added is True
    assert _shipments(db) == [_shipment(1, "TRK-1"), _shipment(2, "TRK-2")]


def test_a_duplicate_shipment_id_passes_through_naming_the_key(profile_run: Any) -> None:
    db = _shipped(profile_run)

    with pytest.raises(DatabaseError) as failed:
        add_a_shipment_unless_its_tracking_number_is_taken(
            db, _shipment(1, "TRK-2"), _tracking_index()
        )

    cause = failed.value
    assert (cause.category, cause.violated_index) == (
        "uniqueViolation",
        PhysicalIndexName("shipment_pkey"),
    )
    assert _shipments(db) == [_shipment(1, "TRK-1")]


def test_an_unrelated_failure_passes_through_the_tracking_number_handler(
    profile_run: Any,
) -> None:
    db = _shipped(profile_run)
    with contextlib.closing(profile_run.control()) as control:
        control.execute_write("drop table shipment", ())

    with pytest.raises(DatabaseError) as failed:
        add_a_shipment_unless_its_tracking_number_is_taken(
            db, _shipment(2, "TRK-2"), _tracking_index()
        )

    cause = failed.value
    assert (cause.category, cause.native_code) == (None, "42P01")


_ORDER_TEN = Order(id=10, customer_id=1, placed_on=dt.date(2024, 4, 1), total=Decimal("150.00"))


def _ordered(profile_run: Any) -> ScopedDatabase:
    db = _shop(profile_run)
    db.transact(lambda tx: tx.insert(_ORDER_TEN))
    return db


def _find_a_missing_customer(_: Any, db: ScopedDatabase) -> object:
    return db.find(Customer.where(Customer.id == 99)).result()


def _delete_at_a_stale_version(_: Any, db: ScopedDatabase) -> object:
    return db.transact(lambda tx: tx.delete_if(Order, key=10, version=7))


def _amend_once_after_another_writer(profile_run: Any, db: ScopedDatabase) -> object:
    def add(tx: TxnContext) -> None:
        order = tx.find(Order.where(Order.id == 10)).result()
        with contextlib.closing(profile_run.control()) as control:
            control.execute_write("update orders set version = version + 1 where id = 10", ())
        tx.amend(order, Order.total.set(order.total + 1))

    return db.transact(add, retry=RetryPolicy(max_retries=0))


def _edit_a_name_away(_: Any, db: ScopedDatabase) -> object:
    return db.find(Customer.where(Customer.id == 1)).result().edit(name=None)


def _delete_payments_by_predicate(_: Any, db: ScopedDatabase) -> object:
    return db.transact(lambda tx: tx.delete_where(Payment.where(Payment.order_id == 10)))


def _find_an_entity_the_model_lacks(_: Any, db: ScopedDatabase) -> object:
    return db.find(Delivery.where(Delivery.all)).results()


def _insert_a_taken_key(_: Any, db: ScopedDatabase) -> object:
    return db.transact(lambda tx: tx.insert(_ORDER_TEN))


@pytest.mark.parametrize(
    ("failing", "kind", "status"),
    [
        pytest.param(_find_a_missing_customer, NoResultFound, 404, id="no-result"),
        pytest.param(_delete_at_a_stale_version, WritePreconditionError, 412, id="precondition"),
        pytest.param(_amend_once_after_another_writer, ConflictError, 409, id="conflict"),
        pytest.param(_edit_a_name_away, EditError, 422, id="refused-edit"),
        pytest.param(_delete_payments_by_predicate, UnsupportedError, 501, id="unsupported"),
        pytest.param(_find_an_entity_the_model_lacks, UsageError, 500, id="usage"),
        pytest.param(_insert_a_taken_key, DatabaseError, 500, id="duplicate-key"),
    ],
)
def test_each_failure_a_request_meets_answers_the_status_its_class_names(
    profile_run: Any,
    failing: Callable[[Any, ScopedDatabase], object],
    kind: type[ParallaxError],
    status: int,
) -> None:
    db = _ordered(profile_run)

    with pytest.raises(kind) as failed:
        failing(profile_run, db)

    assert type(failed.value) is kind
    assert http_status_for(failed.value) == status


def test_a_conflict_that_outlasts_the_retries_answers_409_although_it_is_transient(
    profile_run: Any,
) -> None:
    db = _ordered(profile_run)

    with pytest.raises(ConflictError) as failed:
        _amend_once_after_another_writer(profile_run, db)

    assert failed.value.is_transient
    assert http_status_for(failed.value) == 409


@pytest.mark.parametrize(
    "error",
    [
        pytest.param(InternalError("sql-generation-failed", "scripted"), id="defect"),
        pytest.param(ValueError("scripted"), id="not-parallax"),
    ],
)
def test_a_defect_or_a_foreign_failure_answers_500(error: Exception) -> None:
    assert http_status_for(error) == 500


def test_a_client_query_answers_200_with_its_results(profile_run: Any) -> None:
    db = _shop(profile_run)

    status, body = find_with_a_client_query(
        db, {"target": "Customer", "predicate": {"eq": {"path": "Customer.id", "value": 1}}}
    )

    assert status == 200
    assert isinstance(body, list)
    assert [node["name"] for node in body] == ["Ada"]


@pytest.mark.parametrize(
    ("predicate", "code"),
    [
        pytest.param(
            {"eq": {"path": "Customer.nickname", "value": "Ada"}},
            "path-unknown-member",
            id="unknown-member",
        ),
        pytest.param(
            {"eq": {"path": "Customer.id", "value": "one"}},
            "neutral-literal-type-mismatch",
            id="wrong-type",
        ),
    ],
)
def test_a_refused_client_query_answers_400_with_its_rejected_rule(
    profile_run: Any, predicate: Mapping[str, object], code: str
) -> None:
    db = _shop(profile_run)

    status, body = find_with_a_client_query(db, {"target": "Customer", "predicate": predicate})

    assert status == 400
    assert isinstance(body, dict)
    assert body["code"] == code
    assert code in case_format.rejected_rules()
    assert body["detail"].startswith(f"{code}: ")


def test_a_client_query_naming_an_entity_the_model_lacks_answers_400(profile_run: Any) -> None:
    db = _shop(profile_run)

    status, body = find_with_a_client_query(db, {"target": "Delivery", "predicate": {"true": {}}})

    assert status == 400
    assert isinstance(body, dict)
    assert body["code"] == "query-target-not-in-model"


def test_a_client_query_this_version_cannot_serve_escapes_to_answer_501() -> None:
    db = own_root(Database.connect(RefusingAdapter(), POLICY_MODEL)).using_database_login()
    history_with_includes: Mapping[str, object] = {
        "target": "Policy",
        "predicate": {"true": {}},
        "temporal": {"transaction-time": {"history": {}}, "valid-time": {"asOf": "latest"}},
        "includes": [{"segments": [{"rel": "Policy.coverages"}]}],
    }

    with pytest.raises(UnsupportedError) as failed:
        find_with_a_client_query(db, history_with_includes)

    assert failed.value.code == "execution-feature-deferred"
    assert http_status_for(failed.value) == 501


def test_a_job_that_commits_is_not_retried(profile_run: Any) -> None:
    db = _shop(profile_run)
    later: list[None] = []

    run_or_retry_later(
        db,
        lambda tx: tx.insert(Customer(id=3, name="Grace", email=None)),
        lambda: later.append(None),
    )

    assert later == []
    assert _customer(db, 3) == Customer(id=3, name="Grace", email=None)


def test_a_job_failing_for_good_escapes_instead_of_being_retried(profile_run: Any) -> None:
    db = _shop(profile_run)
    later: list[None] = []

    with pytest.raises(DatabaseError) as failed:
        run_or_retry_later(
            db,
            lambda tx: tx.insert(Customer(id=1, name="Grace", email=None)),
            lambda: later.append(None),
        )

    assert (failed.value.category, failed.value.is_transient) == ("uniqueViolation", False)
    assert later == []


def test_a_jobs_own_exception_escapes_instead_of_being_retried(profile_run: Any) -> None:
    db = _shop(profile_run)
    later: list[None] = []

    def refuse(_: TxnContext) -> None:
        raise LookupError("no such account")

    with pytest.raises(LookupError):
        run_or_retry_later(db, refuse, lambda: later.append(None))

    assert later == []


def test_the_shop_root_serves_reads_and_logs_each_operation(
    profile_run: Any, caplog: pytest.LogCaptureFixture
) -> None:
    profile_run.reset(model_of(SHOP_MODEL), {})
    caplog.set_level(logging.INFO, logger="shop.database")

    with open_the_shop_database(
        profile_run.connection_info, profile_run.credentials, SHOP_MODEL
    ) as root:
        found = root.using_database_login().find(Customer.where(Customer.all)).results()

    assert found == []
    assert [(record.name, record.levelno) for record in caplog.records] == [
        ("shop.database", logging.INFO)
    ]


_CUSTOMER_ROW: Mapping[str, object] = {"id": 1, "name": "Ada", "email": "ada@example.com"}
_GRACE = Customer(id=3, name="Grace", email=None)


def _scripted(adapter: ScriptedAdapter) -> ScopedDatabase:
    return own_root(Database.connect(adapter, SHOP_MODEL)).using_database_login()


@pytest.mark.parametrize(
    ("form", "script", "refused"),
    [
        pytest.param(
            {"email": "ada@example.org"},
            Transact(Read(rows=[_CUSTOMER_ROW]), Write()),
            set[str](),
            id="valid",
        ),
        pytest.param(
            {"name": None},
            Transact(Read(rows=[_CUSTOMER_ROW])),
            {"name"},
            id="refused",
        ),
    ],
)
def test_a_form_runs_through_the_shipped_surface(
    form: Mapping[str, object], script: Transact, refused: set[str]
) -> None:
    with ScriptedAdapter(script) as adapter:
        assert set(change_a_customer_from_a_form(_scripted(adapter), 1, form)) == refused


def _database_error(category: Category | None, native_code: str) -> DatabaseError:
    return DatabaseError(category=category, native_code=native_code, message="scripted")


@pytest.mark.parametrize(
    ("script", "added"),
    [
        pytest.param(Transact(Write()), True, id="added"),
        pytest.param(
            Transact(Write(raises=_database_error("uniqueViolation", "23505"))),
            False,
            id="taken",
        ),
    ],
)
def test_adding_a_customer_runs_through_the_shipped_surface(script: Transact, added: bool) -> None:
    with ScriptedAdapter(script) as adapter:
        assert add_a_customer_unless_the_id_is_taken(_scripted(adapter), _GRACE) is added


def test_another_database_failure_passes_through_the_shipped_surface() -> None:
    with (
        ScriptedAdapter(Transact(Write(raises=_database_error(None, "42P01")))) as adapter,
        pytest.raises(DatabaseError),
    ):
        add_a_customer_unless_the_id_is_taken(_scripted(adapter), _GRACE)


def _unique_violation(index: str | None) -> DatabaseError:
    return DatabaseError(
        category="uniqueViolation",
        native_code="23505",
        message="scripted",
        violated_index=None if index is None else PhysicalIndexName(index),
    )


@pytest.mark.parametrize(
    ("script", "added"),
    [
        pytest.param(Transact(Write()), True, id="added"),
        pytest.param(
            Transact(Write(raises=_unique_violation("pxi_tracking"))), False, id="tracking-taken"
        ),
    ],
)
def test_adding_a_shipment_runs_through_the_shipped_surface(script: Transact, added: bool) -> None:
    with ScriptedAdapter(script) as adapter:
        assert (
            add_a_shipment_unless_its_tracking_number_is_taken(
                _scripted(adapter), _shipment(2, "TRK-1"), PhysicalIndexName("pxi_tracking")
            )
            is added
        )


@pytest.mark.parametrize(
    "error",
    [
        pytest.param(_unique_violation("shipment_pkey"), id="another-index"),
        pytest.param(_unique_violation(None), id="no-index-named"),
        pytest.param(_database_error(None, "42P01"), id="uncategorized"),
    ],
)
def test_any_other_failure_passes_through_the_tracking_number_handler(
    error: DatabaseError,
) -> None:
    with (
        ScriptedAdapter(Transact(Write(raises=error))) as adapter,
        pytest.raises(DatabaseError),
    ):
        add_a_shipment_unless_its_tracking_number_is_taken(
            _scripted(adapter), _shipment(2, "TRK-1"), PhysicalIndexName("pxi_tracking")
        )


_PRICE_ROW: Mapping[str, object] = {
    "sku": "TEA-1",
    "amount": Decimal("4.00"),
    "from_z": _MAR,
    "thru_z": _SEP,
    "in_z": _MAR,
    "out_z": INFINITY,
}
_TEA = Price(sku="TEA-1", amount=Decimal("5.00"))


@pytest.mark.parametrize(
    ("script", "priced"),
    [
        pytest.param(Transact(Read(), Write()), True, id="unpriced"),
        pytest.param(Transact(Read(rows=[_PRICE_ROW])), False, id="priced"),
        pytest.param(
            Transact(Read(), Write(raises=_database_error("uniqueViolation", "23505"))),
            False,
            id="priced-concurrently-to-the-same-end",
        ),
    ],
)
def test_pricing_a_window_runs_through_the_shipped_surface(script: Transact, priced: bool) -> None:
    with ScriptedAdapter(script) as adapter:
        assert price_a_window_unless_it_is_priced(_scripted(adapter), _TEA, _JUN, _DEC) is priced


@pytest.mark.parametrize(
    "error",
    [
        pytest.param(_database_error("constraintViolation", "23P01"), id="unrecognized-overlap"),
        pytest.param(_database_error(None, "42P01"), id="uncategorized"),
    ],
)
def test_any_other_failure_passes_through_the_pricing_handler(error: DatabaseError) -> None:
    with (
        ScriptedAdapter(Transact(Read(), Write(raises=error))) as adapter,
        pytest.raises(DatabaseError),
    ):
        price_a_window_unless_it_is_priced(_scripted(adapter), _TEA, _JUN, _DEC)


def test_a_unique_violation_naming_no_index_surfaces_without_one() -> None:
    unnamed = _database_error("uniqueViolation", "23505")
    with (
        ScriptedAdapter(Transact(Write(raises=unnamed))) as adapter,
        pytest.raises(DatabaseError) as failed,
    ):
        _scripted(adapter).transact(lambda tx: tx.insert(_GRACE))

    cause = failed.value
    assert (cause.category, cause.violated_index) == ("uniqueViolation", None)


def _transient_failures() -> list[Any]:
    return [
        pytest.param(
            lambda: ScriptedAdapter(Transact(Write(raises=_database_error("deadlock", "40P01")))),
            id="deadlock",
        ),
        pytest.param(
            lambda: ScriptedAdapter(
                Transact(Write(raises=_database_error("lockWaitTimeout", "55P03")))
            ),
            id="lock-timeout",
        ),
        pytest.param(
            lambda: ScriptedAdapter(
                acquisition_failures=[
                    ConnectionAcquisitionError("no connection in time", reason="timeout")
                ]
            ),
            id="pool-timeout",
        ),
    ]


def _single_attempt(adapter: ScriptedAdapter) -> ScopedDatabase:
    return _scripted(adapter).with_options(retry=RetryPolicy(max_retries=0))


@pytest.mark.parametrize("adapter", _transient_failures())
def test_a_failure_a_later_run_may_get_past_is_handed_back_to_run_later(
    adapter: Callable[[], ScriptedAdapter],
) -> None:
    later: list[None] = []

    with adapter() as scripted:
        run_or_retry_later(
            _single_attempt(scripted), lambda tx: tx.insert(_GRACE), lambda: later.append(None)
        )

    assert later == [None]


@pytest.mark.parametrize("adapter", _transient_failures())
def test_a_failure_a_later_run_may_get_past_answers_503(
    adapter: Callable[[], ScriptedAdapter],
) -> None:
    with adapter() as scripted, pytest.raises(ParallaxError) as failed:
        _single_attempt(scripted).transact(lambda tx: tx.insert(_GRACE))

    assert failed.value.is_transient
    assert http_status_for(failed.value) == 503


def test_the_shop_root_composes_through_the_shipped_surface(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    opened: list[PostgresAdapter] = []

    def open_scripted(adapter: PostgresAdapter) -> Any:
        opened.append(adapter)
        return ScriptedAdapter().open()

    monkeypatch.setattr(PostgresAdapter, "open", open_scripted)

    with open_the_shop_database(
        "postgresql://shop@localhost/shop", Password("s3cret"), SHOP_MODEL
    ) as root:
        assert type(root) is Database

    assert [adapter.writer.pool.max_size for adapter in opened] == [20]


def test_every_recipe_the_module_exports_has_a_driver() -> None:
    assert sorted(guide_error_recipes.__all__) == sorted(
        recipe.__name__
        for recipe in (
            add_a_customer_unless_the_id_is_taken,
            add_a_shipment_unless_its_tracking_number_is_taken,
            change_a_customer_from_a_form,
            created_index_name,
            find_with_a_client_query,
            http_status_for,
            open_the_shop_database,
            price_a_window_unless_it_is_priced,
            problems_in_a_model,
            run_or_retry_later,
        )
    )
