"""Actor Identity value contract tests."""

from __future__ import annotations

import pytest

from parallax.core.unit_work import DatabaseLoginActor, SubjectActor


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


def test_actor_variants_do_not_compare_equal_for_equal_payloads() -> None:
    assert SubjectActor("login") != DatabaseLoginActor("login")
