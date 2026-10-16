"""The transaction attempt lifetime and the active binding (Docker-free).

What one attempt's lifetime admits — work, a join, a commit — once it is doomed
or closed, which cause it keeps, and how long a bound payload stays visible to
the thread that bound it and to no other.
"""

from __future__ import annotations

import threading

import pytest

from parallax.core._execution._transaction._lifetime import ActiveBinding, TxnAttemptLifetime
from parallax.core._execution._unit_work.uow import EscapedTransactionError
from parallax.core.unit_work import RollbackOnlyError


def test_an_open_lifetime_admits_work_a_join_and_a_commit() -> None:
    lifetime = TxnAttemptLifetime()
    lifetime.ensure_open()
    lifetime.refuse_join()
    lifetime.refuse_commit()
    assert not lifetime.rollback_only


def test_a_doomed_lifetime_refuses_each_with_its_first_cause() -> None:
    lifetime = TxnAttemptLifetime()
    first = RuntimeError("first")
    lifetime.doom(first)
    lifetime.doom(RuntimeError("second"))
    assert lifetime.rollback_only
    for refusal, message in (
        (lifetime.ensure_open, "accepts no further work"),
        (lifetime.refuse_join, "cannot join"),
        (lifetime.refuse_commit, "commit refused"),
    ):
        with pytest.raises(RollbackOnlyError, match=message) as refused:
            refusal()
        assert refused.value.__cause__ is first


def test_a_closed_lifetime_refuses_work_as_an_escaped_reference_before_any_doom() -> None:
    lifetime = TxnAttemptLifetime()
    lifetime.doom(RuntimeError("doomed first"))
    lifetime.close()
    with pytest.raises(EscapedTransactionError):
        lifetime.ensure_open()


def test_a_binding_is_visible_only_while_bound() -> None:
    binding = ActiveBinding[str]()
    assert binding.active() is None
    with binding.bound("attempt"):
        assert binding.active() == "attempt"
    assert binding.active() is None


def test_a_binding_is_cleared_when_its_scope_raises() -> None:
    binding = ActiveBinding[str]()
    with pytest.raises(ValueError, match="callback"), binding.bound("attempt"):
        raise ValueError("callback")
    assert binding.active() is None


def test_a_binding_is_visible_to_the_thread_that_bound_it_alone() -> None:
    binding = ActiveBinding[str]()
    seen: list[str | None] = []
    with binding.bound("attempt"):
        other = threading.Thread(target=lambda: seen.append(binding.active()))
        other.start()
        other.join()
    assert seen == [None]
