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

import pytest

from parallax.core._execution._scope import ExecutionScope
from parallax.core._execution._transaction._attempt import TxnAttempt
from parallax.core.db_port import (
    AccessMode,
    Committed,
    ConnectionAcquisitionError,
    DatabaseConnection,
    IsolationLevel,
    TransactionOutcome,
)
from parallax.core.dialect import POSTGRES, Dialect
from parallax.core.execution import AdaptiveBackoff, RetryPolicy, TxnOptions
from parallax.core.unit_work import SubjectActor
from tests._support.adoption import raises_contextualized
from tests._support.db_port import ConnectsAsItself, ScriptedAdapter, Transact
from tests.unit.core._execution._execution_support import itself, root


@dataclass(frozen=True, slots=True)
class _Principal:
    subject: str
    database_authorization: object


def test_scope_selection_and_option_derivation_acquire_nothing() -> None:
    adapter = ScriptedAdapter()
    database = root(adapter)

    login = database.using_database_login()
    principal = database.using_principal(_Principal("alice", "role-a"))
    login.with_options(retry=RetryPolicy(max_retries=3), concurrency="locking")
    principal.with_options(isolation="serializable")

    assert adapter.acquisitions == 0
    assert adapter.calls == []


def test_an_option_derived_scope_shares_its_authority_runner_and_root_resources() -> None:
    scoped = root(ScriptedAdapter()).using_database_login()
    derived = cast("Any", scoped.with_options(retry=RetryPolicy(max_retries=3)))
    unchanged = cast("Any", scoped.with_options())
    private = cast("Any", scoped)

    assert derived._authority is private._authority
    assert derived._runner is private._runner
    assert derived._planner is private._planner
    assert derived._serving is private._serving
    assert derived._options == TxnOptions(retry=RetryPolicy(max_retries=3))
    assert unchanged._options is private._options


def test_a_derived_policy_replaces_the_scopes_whole_and_an_omitted_one_inherits_it() -> None:
    tuned = RetryPolicy(max_retries=4, backoff=AdaptiveBackoff(base_delay=0.5, max_delay=2.0))
    scoped = root(ScriptedAdapter()).using_database_login().with_options(retry=tuned)

    inherited = cast("Any", scoped.with_options(isolation="serializable"))
    replaced = cast("Any", scoped.with_options(retry=RetryPolicy(max_retries=1)))

    assert inherited._options.retry is tuned
    assert replaced._options.retry == RetryPolicy(max_retries=1, backoff=AdaptiveBackoff())


def test_an_equal_policy_reuses_the_scopes_record() -> None:
    scoped = root(ScriptedAdapter()).using_database_login()

    unchanged = cast("Any", scoped.with_options(retry=RetryPolicy()))

    assert unchanged._options is cast("Any", scoped)._options


@pytest.mark.parametrize("value", [None, 3, True, AdaptiveBackoff()])
def test_derivation_refuses_a_value_that_is_no_policy_without_acquiring(value: object) -> None:
    adapter = ScriptedAdapter()
    database = root(adapter)
    scoped = database.using_database_login()

    with pytest.raises(ValueError, match="retry must be a RetryPolicy"):
        scoped.with_options(retry=cast("Any", value))
    with pytest.raises(ValueError, match="retry must be a RetryPolicy"):
        database.with_options(retry=cast("Any", value))

    assert adapter.acquisitions == 0
    assert adapter.calls == []


def test_root_alias_options_are_independent_while_resources_and_close_are_shared() -> None:
    adapter = ScriptedAdapter(Transact())
    database = root(adapter)
    alias = database.with_options(retry=RetryPolicy(max_retries=0), isolation="serializable")
    original_scope = database.using_database_login()
    alias_scope = alias.using_database_login()

    assert isinstance(alias_scope, ExecutionScope)
    assert original_scope.transact(lambda attempt: attempt.options, itself) == TxnOptions()
    assert adapter.acquisitions == 1
    alias.close()

    with raises_contextualized(ConnectionAcquisitionError) as closed:
        original_scope.transact(lambda _attempt: None, itself)
    assert closed.value.reason == "closed"


def test_explicit_scope_defaults_do_not_conflict_with_a_join() -> None:
    database = root(ScriptedAdapter(Transact()))
    outer = database.using_database_login().with_options(retry=RetryPolicy(max_retries=1))
    joining = database.using_database_login().with_options(
        retry=RetryPolicy(max_retries=9), isolation="serializable"
    )

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
        access_mode: AccessMode | None = None,
    ) -> TransactionOutcome[T]:
        del isolation, access_mode
        self._entered.wait(timeout=5)
        return Committed(body(cast("DatabaseConnection", self)))


def test_concurrent_scopes_keep_their_own_authority_and_defaults() -> None:
    database = root(_InterleavingPort())
    alice = database.using_principal(_Principal("alice", "role-a")).with_options(
        retry=RetryPolicy(max_retries=1), isolation="serializable"
    )
    bob = database.using_principal(_Principal("bob", "role-b")).with_options(
        retry=RetryPolicy(max_retries=4), isolation="repeatable_read"
    )

    def observe(scope: ExecutionScope) -> tuple[object, TxnOptions]:
        def body(attempt: TxnAttempt) -> tuple[object, TxnOptions]:
            actor = attempt.uow._actor_identity  # pyright: ignore[reportPrivateUsage] - the actor each attempt plans under is the claim
            return actor, attempt.options

        return scope.transact(body, itself)

    with ThreadPoolExecutor(max_workers=2) as executor:
        alice_result = executor.submit(observe, alice)
        bob_result = executor.submit(observe, bob)

    assert alice_result.result() == (
        SubjectActor("alice"),
        TxnOptions(retry=RetryPolicy(max_retries=1), isolation="serializable"),
    )
    assert bob_result.result() == (
        SubjectActor("bob"),
        TxnOptions(retry=RetryPolicy(max_retries=4), isolation="repeatable_read"),
    )
