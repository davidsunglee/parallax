"""Database Root and immutable scoped-execution surface boundaries."""

from __future__ import annotations

import threading
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Any, cast

import pytest

from parallax.core.db_port import (
    Committed,
    ConnectionAcquisitionError,
    DatabaseConnection,
    IsolationLevel,
    TransactionOutcome,
)
from parallax.core.dialect import POSTGRES, Dialect
from parallax.core.unit_work import FixedClock, SubjectActor
from parallax.snapshot import DatabaseOptions
from parallax.snapshot.handle import Database, ScopedDatabase
from tests._support.adoption import raises_contextualized
from tests._support.db_port import ConnectsAsItself, ScriptedAdapter, Transact
from tests.unit._transact_support import ACCOUNT, FIXED


def test_root_and_scope_expose_disjoint_ownership_and_execution_surfaces() -> None:
    root = Database.connect(ScriptedAdapter(), ACCOUNT, clock=FixedClock(FIXED))
    scoped = root.using_database_login()

    assert not hasattr(root, "find")
    assert not hasattr(root, "stream")
    assert not hasattr(root, "wire")
    assert not hasattr(root, "read_rows")
    assert not hasattr(root, "transact")
    assert not hasattr(scoped, "close")
    assert not hasattr(scoped, "__enter__")
    assert not hasattr(scoped, "using_principal")
    assert not hasattr(scoped, "using_database_login")


def test_scopes_are_immutable_and_only_roots_can_construct_them() -> None:
    root = Database.connect(ScriptedAdapter(), ACCOUNT, clock=FixedClock(FIXED))
    scoped = root.using_database_login()

    with pytest.raises(TypeError, match="authority selection"):
        ScopedDatabase()
    with pytest.raises(AttributeError, match="immutable"):
        scoped.extra = "changed"


def test_scope_selection_and_option_derivation_acquire_nothing() -> None:
    adapter = ScriptedAdapter()
    root = Database.connect(adapter, ACCOUNT, clock=FixedClock(FIXED))

    login = root.using_database_login()
    principal = root.using_principal(
        cast(
            "Any",
            type("PrincipalValue", (), {"subject": "alice", "database_authorization": "role-a"})(),
        )
    )
    login.with_options(max_retries=3, concurrency="locking")
    principal.with_options(isolation="serializable")

    assert adapter.acquisitions == 0
    assert adapter.calls == []


def test_option_derived_scope_reuses_capture_runner_and_read_composition() -> None:
    root = Database.connect(ScriptedAdapter(), ACCOUNT, clock=FixedClock(FIXED))
    scoped = root.using_database_login()
    derived = scoped.with_options(max_retries=3)
    unchanged = scoped.with_options()

    private_scoped = cast("Any", scoped)
    private_derived = cast("Any", derived)
    private_unchanged = cast("Any", unchanged)
    assert private_derived._capture is private_scoped._capture
    assert private_derived._transaction_runner is private_scoped._transaction_runner
    assert private_derived._reads is private_scoped._reads
    assert private_derived._options == DatabaseOptions(max_retries=3)
    assert private_unchanged._options is private_scoped._options


def test_root_alias_options_are_independent_while_resources_and_close_are_shared() -> None:
    adapter = ScriptedAdapter(Transact())
    root = Database.connect(adapter, ACCOUNT, clock=FixedClock(FIXED))
    alias = root.with_options(max_retries=0, isolation="serializable")
    original_scope = root.using_database_login()
    alias_scope = alias.using_database_login()

    assert isinstance(alias_scope, ScopedDatabase)
    assert original_scope.transact(lambda tx: tx.options) == DatabaseOptions()
    assert adapter.acquisitions == 1
    alias.close()

    with raises_contextualized(ConnectionAcquisitionError) as closed:
        original_scope.transact(lambda _tx: None)
    assert closed.value.reason == "closed"


def test_explicit_scope_defaults_do_not_conflict_with_a_join() -> None:
    adapter = ScriptedAdapter(Transact())
    root = Database.connect(adapter, ACCOUNT, clock=FixedClock(FIXED))
    outer = root.using_database_login().with_options(max_retries=1)
    joining = root.using_database_login().with_options(max_retries=9, isolation="serializable")

    assert outer.transact(lambda tx: joining.transact(lambda joined: joined is tx))


@dataclass(frozen=True, slots=True)
class _Principal:
    subject: str
    database_authorization: object


def test_required_scope_arguments_are_positional_only() -> None:
    root = Database.connect(ScriptedAdapter(), ACCOUNT, clock=FixedClock(FIXED))
    principal = _Principal("alice", "role-a")
    scoped = root.using_database_login()

    with pytest.raises(TypeError):
        cast("Any", root.using_principal)(principal=principal)

    def no_op(_tx: Any) -> None:
        return None

    with pytest.raises(TypeError):
        cast("Any", scoped.transact)(fn=no_op)


class _InterleavingPort(ConnectsAsItself):
    dialect: Dialect = POSTGRES

    def __init__(self) -> None:
        self._entered = threading.Barrier(2)

    def transaction[T](
        self,
        body: Callable[[DatabaseConnection], T],
        *,
        isolation: IsolationLevel | None = None,
    ) -> TransactionOutcome[T]:
        del isolation
        self._entered.wait(timeout=5)
        return Committed(body(cast("DatabaseConnection", self)))


def test_concurrent_scopes_keep_their_own_authority_and_defaults() -> None:
    with Database.connect(_InterleavingPort(), ACCOUNT, clock=FixedClock(FIXED)) as root:
        alice = root.using_principal(_Principal("alice", "role-a")).with_options(
            max_retries=1, isolation="serializable"
        )
        bob = root.using_principal(_Principal("bob", "role-b")).with_options(
            max_retries=4, isolation="repeatable_read"
        )

        def observe(scope: ScopedDatabase) -> tuple[object, DatabaseOptions]:
            def body(tx: Any) -> tuple[object, DatabaseOptions]:
                actor = tx._uow._actor_identity
                return actor, tx.options

            return scope.transact(body)

        with ThreadPoolExecutor(max_workers=2) as executor:
            alice_result = executor.submit(observe, alice)
            bob_result = executor.submit(observe, bob)

    assert alice_result.result() == (
        SubjectActor("alice"),
        DatabaseOptions(max_retries=1, isolation="serializable"),
    )
    assert bob_result.result() == (
        SubjectActor("bob"),
        DatabaseOptions(max_retries=4, isolation="repeatable_read"),
    )
