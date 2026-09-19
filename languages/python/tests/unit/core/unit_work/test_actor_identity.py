"""Actor Identity value and neutral audit-projection contract tests."""

from __future__ import annotations

import pytest

from parallax.core.unit_work import (
    DatabaseLoginActor,
    SubjectActor,
    actor_identity_to_audit_string,
)


@pytest.mark.parametrize("value", ["", None, 7])
def test_a_subject_actor_requires_a_nonempty_string(value: object) -> None:
    with pytest.raises(ValueError, match="nonempty string"):
        SubjectActor(value)  # type: ignore[arg-type] - runtime validation is the contract under test


def test_a_subject_actor_reserves_the_database_login_prefix() -> None:
    with pytest.raises(ValueError, match="must not begin with 'db-login:'"):
        SubjectActor("db-login:application-forgery")


@pytest.mark.parametrize("value", ["", None, 7])
def test_a_database_login_actor_requires_a_nonempty_string(value: object) -> None:
    with pytest.raises(ValueError, match="nonempty string"):
        DatabaseLoginActor(value)  # type: ignore[arg-type] - runtime validation is the contract under test


@pytest.mark.parametrize("value", ["alice", " Alice ", "ALICE"])
def test_a_subject_actor_projects_verbatim(value: str) -> None:
    assert actor_identity_to_audit_string(SubjectActor(value)) == value


def test_a_database_login_actor_projects_with_the_reserved_prefix() -> None:
    actor = DatabaseLoginActor("runtime_login")
    assert actor_identity_to_audit_string(actor) == "db-login:runtime_login"


def test_actor_projection_does_not_parse_or_escape_database_login_content() -> None:
    actor = DatabaseLoginActor(" db-login:Runner ")
    assert actor_identity_to_audit_string(actor) == "db-login: db-login:Runner "


def test_actor_variants_do_not_compare_equal_for_equal_payloads() -> None:
    assert SubjectActor("login") != DatabaseLoginActor("login")
