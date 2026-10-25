"""The Python Guide's execution-authority recipes against real Postgres.

Each recipe's source is a published snippet, so these tests grade the outcome a
reader is told to expect. The database-free run-throughs at the end drive every
recipe body through the shipped surface over a scripted port.
"""

from __future__ import annotations

import contextlib
import datetime as dt
from collections.abc import Mapping
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from parallax.conformance import guide_authority_recipes
from parallax.conformance.guide_authority_recipes import (
    SecretFile,
    ShopUser,
    another_user_can_join,
    change_an_email_for,
    configure_with_a_secret_file,
    orders_for_the_nightly_report,
    rename_a_customer,
)
from parallax.conformance.guide_models import SHOP_MODEL, Customer, Order
from parallax.core.entity import model_of
from parallax.core.execution import ExecutionFailure
from parallax.postgres import PostgresAdapter, PostgresRole
from parallax.snapshot import Database, connect
from tests._support.db_port import Read, ScriptedAdapter, Transact, Write
from tests._support.root_ownership import own_root

_APRIL_FIRST = dt.date(2024, 4, 1)


def _shop_root(profile_run: Any) -> Database[PostgresRole]:
    profile_run.reset(model_of(SHOP_MODEL), {})
    root = own_root(connect(profile_run.port, SHOP_MODEL))
    root.using_database_login().transact(
        lambda tx: (
            tx.insert(Customer(id=1, name="Ada", email="ada@example.com")),
            tx.insert(Order(id=10, customer_id=1, placed_on=_APRIL_FIRST, total=Decimal("150.00"))),
            tx.insert(
                Order(id=11, customer_id=1, placed_on=dt.date(2024, 4, 9), total=Decimal("20.00"))
            ),
        )
    )
    return root


def _customer_one(root: Database[PostgresRole]) -> Customer:
    return root.using_database_login().find(Customer.where(Customer.id == 1)).result()


def test_scheduled_work_reads_under_the_service_login(profile_run: Any) -> None:
    root = _shop_root(profile_run)

    orders = orders_for_the_nightly_report(root, _APRIL_FIRST)

    assert [order.id for order in orders] == [10]


def test_a_request_runs_with_its_users_role_in_place_of_the_logins_privileges(
    profile_run: Any,
) -> None:
    root = _shop_root(profile_run)
    clerk = ShopUser("user:clerk", profile_run.authorization("role-a"))
    viewer = ShopUser("user:viewer", profile_run.authorization("role-b"))
    with contextlib.closing(profile_run.control()) as control:
        control.execute_write(
            f'revoke update on customer from "{viewer.database_authorization.name}"', ()
        )

    change_an_email_for(root, clerk, 1, "ada@example.org")
    with pytest.raises(ExecutionFailure) as refused:
        change_an_email_for(root, viewer, 1, "ada@example.net")

    assert "permission denied" in str(refused.value.cause)
    assert _customer_one(root).email == "ada@example.org"


def test_the_password_is_read_when_a_connection_is_made_not_when_configured(
    profile_run: Any, tmp_path: Path
) -> None:
    profile_run.reset(model_of(SHOP_MODEL), {})
    secret = tmp_path / "password"
    secret.write_text("not-the-password\n", encoding="utf-8")
    adapter = configure_with_a_secret_file(profile_run.connection_info, secret)
    secret.write_text(f"{profile_run.credentials.secret}\n", encoding="utf-8")

    with connect(adapter, SHOP_MODEL) as root:
        found = root.using_database_login().find(Customer.where(Customer.all)).results()

    assert found == []


@pytest.mark.parametrize(
    ("other_subject", "other_role", "joined", "name"),
    [
        pytest.param("user:ada", "role-a", True, "Ada Lovelace", id="same-user"),
        pytest.param("user:grace", "role-a", False, "Ada King", id="another-user"),
        pytest.param("user:ada", "role-b", False, "Ada King", id="same-user-another-role"),
    ],
)
def test_only_the_same_actor_joins_a_running_transaction(
    profile_run: Any, other_subject: str, other_role: str, joined: bool, name: str
) -> None:
    root = _shop_root(profile_run)
    user = ShopUser("user:ada", profile_run.authorization("role-a"))
    other = ShopUser(other_subject, profile_run.authorization(other_role))

    assert another_user_can_join(root, user, other, 1) is joined
    assert _customer_one(root).name == name


_CUSTOMER_ROW: Mapping[str, object] = {"id": 1, "name": "Ada", "email": "ada@example.com"}
_ORDER_ROW: Mapping[str, object] = {
    "id": 10,
    "customer_id": 1,
    "placed_on": _APRIL_FIRST,
    "total": Decimal("150.00"),
    "version": 1,
}
_CLERK = ShopUser("user:clerk", PostgresRole("shop_clerk"))


def test_the_nightly_report_runs_through_the_shipped_surface() -> None:
    with ScriptedAdapter(Read(rows=[_ORDER_ROW])) as adapter:
        orders = orders_for_the_nightly_report(
            own_root(Database.connect(adapter, SHOP_MODEL)), _APRIL_FIRST
        )

    assert [order.id for order in orders] == [10]


def test_a_users_request_runs_through_the_shipped_surface() -> None:
    with ScriptedAdapter(Transact(Read(rows=[_CUSTOMER_ROW]), Write())) as adapter:
        change_an_email_for(
            own_root(Database.connect(adapter, SHOP_MODEL)), _CLERK, 1, "ada@example.org"
        )


def test_a_secret_file_is_read_through_the_configured_adapter(tmp_path: Path) -> None:
    secret = tmp_path / "password"
    secret.write_text("s3cret\n", encoding="utf-8")

    adapter = configure_with_a_secret_file("postgresql://shop@localhost/shop", secret)

    assert type(adapter) is PostgresAdapter
    assert isinstance(adapter.credentials, SecretFile)
    assert adapter.credentials.resolve().secret == "s3cret"


@pytest.mark.parametrize(
    ("other", "script", "joined"),
    [
        pytest.param(
            _CLERK,
            Transact(Read(rows=[_CUSTOMER_ROW]), Write(), Read(rows=[_CUSTOMER_ROW]), Write()),
            True,
            id="same-user",
        ),
        pytest.param(
            ShopUser("user:manager", PostgresRole("shop_clerk")),
            Transact(Read(rows=[_CUSTOMER_ROW]), Write()),
            False,
            id="another-user",
        ),
    ],
)
def test_joining_under_one_actor_runs_through_the_shipped_surface(
    other: ShopUser, script: Transact, joined: bool
) -> None:
    with ScriptedAdapter(script) as adapter:
        database = own_root(Database.connect(adapter, SHOP_MODEL))

        assert another_user_can_join(database, _CLERK, other, 1) is joined


def test_every_recipe_the_module_exports_has_a_driver() -> None:
    assert sorted(guide_authority_recipes.__all__) == sorted(
        recipe.__name__
        for recipe in (
            SecretFile,
            ShopUser,
            another_user_can_join,
            change_an_email_for,
            configure_with_a_secret_file,
            orders_for_the_nightly_report,
            rename_a_customer,
        )
    )
