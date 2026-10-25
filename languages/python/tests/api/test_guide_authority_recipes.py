"""The Python Guide's execution-authority recipes against real Postgres.

Each recipe's source is a published snippet, so these tests grade the outcome a
reader is told to expect. The database-free run-throughs at the end drive every
recipe body through the shipped surface over a scripted port.
"""

from __future__ import annotations

import ast
import builtins
import contextlib
import datetime as dt
import re
from collections.abc import Mapping
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from parallax.conformance import case_format, guide_authority_recipes, guide_models
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
from parallax.conformance.usage_guide import snippet_sources
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
        elif isinstance(node, ast.ExceptHandler) and node.name is not None:
            bound.add(node.name)
        elif isinstance(node, ast.Name):
            (bound if isinstance(node.ctx, ast.Store) else loaded).add(node.id)
    return bound, loaded


_GUIDE = case_format.find_repo_root() / "languages" / "python" / "docs" / "guide"
_MARKER = re.compile(r"<!-- example: ([a-z0-9][a-z0-9-]*) -->")
_EXAMPLE_BLOCK = re.compile(r"<!-- example: .*?<!-- /example -->", re.DOTALL)
_CODE_SPAN = re.compile(r"`([^`\n]+)`")
_SHOP_MODEL_NAMES: frozenset[str] = frozenset(guide_models.__all__) - {"SHOP_MODEL"}


@pytest.mark.parametrize(
    ("chapter", "imports_id"),
    [pytest.param("06-execution-authority.md", "execution-authority-imports", id="06")],
)
def test_each_chapters_imports_bind_what_its_snippets_read_and_only_what_it_names(
    chapter: str, imports_id: str
) -> None:
    # A reader finds every name a chapter uses in its imports block. The block
    # has to resolve, cover every name the chapter's snippets read beyond the
    # shop model, and import nothing the chapter neither reads in a snippet nor
    # names in its prose.
    text = (_GUIDE / chapter).read_text(encoding="utf-8")
    sources = snippet_sources()
    marked = _MARKER.findall(text)
    assert imports_id in marked
    imports = sources[imports_id]
    exec(compile(imports, imports_id, "exec"), {})
    bound, loaded = _bound_and_loaded("\n\n".join(sources[source_id] for source_id in marked))
    imported, _ = _bound_and_loaded(imports)
    named = {
        name
        for span in _CODE_SPAN.findall(_EXAMPLE_BLOCK.sub("", text))
        for name in re.findall(r"[A-Za-z_][A-Za-z0-9_]*", span)
    }

    assert loaded - bound - set(dir(builtins)) - _SHOP_MODEL_NAMES == set()
    assert imported - loaded - named == set()
