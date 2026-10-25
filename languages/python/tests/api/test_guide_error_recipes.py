"""The Python Guide's Errors and Operations recipes against real Postgres.

Each recipe's source is a published snippet, so these tests grade the outcome a
reader is told to expect, reading database failures through public attributes
only. The database-free run-throughs at the end drive every recipe body through
the shipped surface over a scripted port.
"""

from __future__ import annotations

import contextlib
import logging
from collections.abc import Mapping
from typing import Any

import pytest

from parallax.conformance import guide_error_recipes
from parallax.conformance.guide_error_recipes import (
    add_a_customer_unless_the_id_is_taken,
    change_a_customer_from_a_form,
    open_the_shop_database,
)
from parallax.conformance.guide_models import SHOP_MODEL, Customer
from parallax.core.db_error import DatabaseError
from parallax.core.db_port import Password
from parallax.core.entity import model_of
from parallax.core.execution import ExecutionFailure
from parallax.postgres import PostgresAdapter
from parallax.snapshot import Database, ScopedDatabase, connect
from tests._support.db_port import Read, ScriptedAdapter, Transact, Write
from tests._support.root_ownership import own_root


def _shop(profile_run: Any) -> ScopedDatabase:
    profile_run.reset(model_of(SHOP_MODEL), {})
    db = own_root(connect(profile_run.port, SHOP_MODEL)).using_database_login()
    db.transact(lambda tx: tx.insert(Customer(id=1, name="Ada", email="ada@example.com")))
    return db


def _customer(db: ScopedDatabase, customer_id: int) -> Customer | None:
    return db.find(Customer.where(Customer.id == customer_id)).result_or_none()


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

    with pytest.raises(ExecutionFailure) as failed:
        db.transact(lambda tx: tx.insert(Customer(id=1, name="Grace", email=None)))

    cause: Any = failed.value.cause
    assert (cause.category, cause.native_code) == ("uniqueViolation", "23505")
    assert "customer_pkey" in cause.message


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


def test_a_database_failure_with_another_category_passes_through(profile_run: Any) -> None:
    db = _shop(profile_run)
    with contextlib.closing(profile_run.control()) as control:
        control.execute_write("drop table customer", ())

    with pytest.raises(ExecutionFailure) as failed:
        add_a_customer_unless_the_id_is_taken(db, Customer(id=3, name="Grace", email=None))

    cause: Any = failed.value.cause
    assert (cause.category, cause.native_code) == (None, "42P01")


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


def _database_error(category: Any, native_code: str) -> DatabaseError:
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
        pytest.raises(ExecutionFailure),
    ):
        add_a_customer_unless_the_id_is_taken(_scripted(adapter), _GRACE)


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

    assert [adapter.pool.max_size for adapter in opened] == [20]


def test_every_recipe_the_module_exports_has_a_driver() -> None:
    assert sorted(guide_error_recipes.__all__) == sorted(
        recipe.__name__
        for recipe in (
            add_a_customer_unless_the_id_is_taken,
            change_a_customer_from_a_form,
            open_the_shop_database,
        )
    )
