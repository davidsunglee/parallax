"""Execution-authority capture and value comparison."""

from __future__ import annotations

import gc
import weakref
from dataclasses import dataclass
from typing import Any

import pytest

from parallax.core.db_port import InvalidAuthorizationError
from parallax.snapshot.handle._execution_authority import (
    InvalidPrincipalError,
    LoginExecution,
    PrincipalExecution,
    capture_database_login,
    capture_principal,
    same_execution,
)
from tests._support.db_port import ScriptedAdapter


@dataclass(frozen=True, slots=True)
class _Authorization:
    name: str


class _Principal:
    def __init__(self, subject: object, authorization: object, reads: list[str]) -> None:
        self.current_subject = subject
        self.current_authorization = authorization
        self.reads = reads

    @property
    def subject(self) -> Any:
        self.reads.append("subject")
        return self.current_subject

    @property
    def database_authorization(self) -> Any:
        self.reads.append("authorization")
        return self.current_authorization


class _RefusingRuntime:
    login_identity = "runner"

    def principal_execution(self, authorization: object) -> Any:
        del authorization
        raise InvalidAuthorizationError("unsupported authorization")


def test_capture_reads_properties_once_in_order_and_retains_only_values() -> None:
    runtime = ScriptedAdapter().open()
    reads: list[str] = []
    authorization = _Authorization("role-a")
    principal = _Principal("alice", authorization, reads)
    retained = weakref.ref(principal)

    capture = capture_principal(runtime, principal)
    principal.current_subject = "bob"
    principal.current_authorization = _Authorization("role-b")
    del principal
    gc.collect()

    assert reads == ["subject", "authorization"]
    assert capture.actor.value == "alice"
    assert capture.authorization is authorization
    assert retained() is None


@pytest.mark.parametrize("subject", [None, "", "db-login:runner"])
def test_invalid_subjects_are_translated_with_the_actor_error_as_cause(subject: object) -> None:
    principal = _Principal(subject, _Authorization("role-a"), [])

    with pytest.raises(InvalidPrincipalError) as refused:
        capture_principal(ScriptedAdapter().open(), principal)

    assert isinstance(refused.value.__cause__, ValueError)


def test_invalid_authorization_is_translated_with_the_provider_error_as_cause() -> None:
    principal = _Principal("alice", _Authorization("role-a"), [])

    with pytest.raises(InvalidPrincipalError) as refused:
        capture_principal(_RefusingRuntime(), principal)  # type: ignore[arg-type]

    assert isinstance(refused.value.__cause__, InvalidAuthorizationError)


def test_property_and_unexpected_provider_errors_propagate_unchanged() -> None:
    property_error = InvalidAuthorizationError("application property failed")

    class PropertyFailure:
        @property
        def subject(self) -> str:
            raise property_error

        @property
        def database_authorization(self) -> object:
            raise AssertionError("authorization must not be read")

    with pytest.raises(InvalidAuthorizationError) as from_property:
        capture_principal(ScriptedAdapter().open(), PropertyFailure())
    assert from_property.value is property_error

    provider_error = RuntimeError("provider failed unexpectedly")

    class ProviderFailure:
        login_identity = "runner"

        def principal_execution(self, authorization: object) -> Any:
            del authorization
            raise provider_error

    with pytest.raises(RuntimeError) as from_provider:
        capture_principal(
            ProviderFailure(),  # type: ignore[arg-type]
            _Principal("alice", _Authorization("role-a"), []),
        )
    assert from_provider.value is provider_error


def test_execution_equality_uses_captured_values_not_sources_or_identity() -> None:
    runtime = ScriptedAdapter().open()
    first_subject = " alice"[1:]
    second_subject = "alice "[:-1]
    first_authorization = _Authorization("role-a")
    second_authorization = _Authorization("role-a")

    first = capture_principal(runtime, _Principal(first_subject, first_authorization, []))
    second = capture_principal(runtime, _Principal(second_subject, second_authorization, []))
    different_subject = capture_principal(runtime, _Principal("bob", second_authorization, []))
    different_authorization = capture_principal(
        runtime, _Principal("alice", _Authorization("role-b"), [])
    )
    login_a = capture_database_login(runtime)
    login_b = capture_database_login(runtime)

    assert first_subject == second_subject and first_subject is not second_subject
    assert first_authorization == second_authorization
    assert first_authorization is not second_authorization
    assert isinstance(first, PrincipalExecution)
    assert isinstance(login_a, LoginExecution)
    assert first.source is not second.source
    assert login_a.source is not login_b.source
    assert same_execution(first, second)
    assert not same_execution(first, different_subject)
    assert not same_execution(first, different_authorization)
    assert not same_execution(first, login_a)
    assert same_execution(login_a, login_b)
