"""Database Roots and the authority-selected Execution Scopes they answer.

Every scope here is the actual Execution Scope a root's scope factory receives,
and every transaction callback receives the actual Attempt, over the scripted
port. What a lifecycle's facade adds over a scope — its own type, its
immutability, and the verbs it publishes — is that lifecycle's suite's.
"""

from __future__ import annotations

import threading
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Any, cast

from parallax.core.db_port import (
    Committed,
    ConnectionAcquisitionError,
    DatabaseConnection,
    IsolationLevel,
    TransactionOutcome,
)
from parallax.core.dialect import POSTGRES, Dialect
from parallax.core.execution import DatabaseOptions
from parallax.core.execution._attempt import Attempt
from parallax.core.execution._scope import ExecutionScope
from parallax.core.unit_work import SubjectActor
from tests._support.adoption import raises_contextualized
from tests._support.db_port import ConnectsAsItself, ScriptedAdapter, Transact
from tests.unit.core.execution._execution_support import itself, root


@dataclass(frozen=True, slots=True)
class _Principal:
    subject: str
    database_authorization: object


def test_scope_selection_and_option_derivation_acquire_nothing() -> None:
    adapter = ScriptedAdapter()
    database = root(adapter)

    login = database.using_database_login()
    principal = database.using_principal(_Principal("alice", "role-a"))
    login.with_options(max_retries=3, concurrency="locking")
    principal.with_options(isolation="serializable")

    assert adapter.acquisitions == 0
    assert adapter.calls == []


def test_an_option_derived_scope_shares_its_authority_runner_and_root_resources() -> None:
    scoped = root(ScriptedAdapter()).using_database_login()
    derived = cast("Any", scoped.with_options(max_retries=3))
    unchanged = cast("Any", scoped.with_options())
    private = cast("Any", scoped)

    assert derived._capture is private._capture
    assert derived._runner is private._runner
    assert derived._planner is private._planner
    assert derived._serving is private._serving
    assert derived._options == DatabaseOptions(max_retries=3)
    assert unchanged._options is private._options


def test_root_alias_options_are_independent_while_resources_and_close_are_shared() -> None:
    adapter = ScriptedAdapter(Transact())
    database = root(adapter)
    alias = database.with_options(max_retries=0, isolation="serializable")
    original_scope = database.using_database_login()
    alias_scope = alias.using_database_login()

    assert isinstance(alias_scope, ExecutionScope)
    assert original_scope.transact(lambda attempt: attempt.options, itself) == DatabaseOptions()
    assert adapter.acquisitions == 1
    alias.close()

    with raises_contextualized(ConnectionAcquisitionError) as closed:
        original_scope.transact(lambda _attempt: None, itself)
    assert closed.value.reason == "closed"


def test_explicit_scope_defaults_do_not_conflict_with_a_join() -> None:
    database = root(ScriptedAdapter(Transact()))
    outer = database.using_database_login().with_options(max_retries=1)
    joining = database.using_database_login().with_options(max_retries=9, isolation="serializable")

    assert outer.transact(
        lambda attempt: joining.transact(lambda joined: joined is attempt, itself), itself
    )


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
    database = root(_InterleavingPort())
    alice = database.using_principal(_Principal("alice", "role-a")).with_options(
        max_retries=1, isolation="serializable"
    )
    bob = database.using_principal(_Principal("bob", "role-b")).with_options(
        max_retries=4, isolation="repeatable_read"
    )

    def observe(scope: ExecutionScope) -> tuple[object, DatabaseOptions]:
        def body(attempt: Attempt) -> tuple[object, DatabaseOptions]:
            actor = attempt.uow._actor_identity  # pyright: ignore[reportPrivateUsage] - the actor each attempt plans under is the claim
            return actor, attempt.options

        return scope.transact(body, itself)

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
