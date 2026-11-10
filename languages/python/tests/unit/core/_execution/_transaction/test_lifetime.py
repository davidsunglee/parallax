"""The transaction attempt lifetime and the active binding (Docker-free).

What one attempt's lifetime admits — work, a join, a commit — once it is doomed,
which cause it keeps, and that a bound payload stays visible to the thread that
bound it and to no other.
"""

from __future__ import annotations

import threading

import pytest

from parallax.core import ConflictError, DatabaseError, UsageError, WritePreconditionError
from parallax.core._execution._transaction._lifetime import ActiveBinding, TxnAttemptLifetime
from parallax.core.internal.metamodel import EntityIdentity
from parallax.core.internal.unit_work import TRANSACTION_ROLLBACK_ONLY
from tests._support.errors import raises_code


def test_an_open_lifetime_admits_work_a_join_and_a_commit() -> None:
    lifetime = TxnAttemptLifetime()
    lifetime.ensure_open()
    lifetime.refuse_join()
    lifetime.refuse_commit()


def test_a_doomed_lifetime_refuses_each_with_its_first_cause() -> None:
    lifetime = TxnAttemptLifetime()
    first = RuntimeError("first")
    lifetime.doom(first)
    lifetime.doom(RuntimeError("second"))
    for refusal, message in (
        (lifetime.ensure_open, "accepts no further work"),
        (lifetime.refuse_join, "cannot join"),
        (lifetime.refuse_commit, "commit refused"),
    ):
        with raises_code(UsageError, TRANSACTION_ROLLBACK_ONLY, match=message) as refused:
            refusal()
        assert refused.value.__cause__ is first


@pytest.mark.parametrize(
    ("cause", "transient"),
    [
        pytest.param(
            ConflictError("optimistic-lock-conflict", "m", transient=True), True, id="conflict"
        ),
        pytest.param(
            DatabaseError(category="deadlock", native_code="40P01", message="m"),
            True,
            id="deadlock",
        ),
        pytest.param(
            WritePreconditionError(EntityIdentity("shop", "Order"), {"id": 1}, 3),
            False,
            id="precondition",
        ),
        pytest.param(
            DatabaseError(category="uniqueViolation", native_code="23505", message="m"),
            False,
            id="duplicate-key",
        ),
        pytest.param(LookupError("the application's own"), False, id="application"),
    ],
)
def test_a_rollback_only_refusal_is_transient_exactly_when_its_cause_is(
    cause: Exception, transient: bool
) -> None:
    lifetime = TxnAttemptLifetime()
    lifetime.doom(cause)
    for refusal in (lifetime.ensure_open, lifetime.refuse_join, lifetime.refuse_commit):
        with raises_code(UsageError, TRANSACTION_ROLLBACK_ONLY) as refused:
            refusal()
        assert refused.value.is_transient is transient


def test_a_binding_is_visible_to_the_thread_that_bound_it_alone() -> None:
    binding = ActiveBinding[str]()
    seen: list[str | None] = []
    with binding.bound("attempt"):
        other = threading.Thread(target=lambda: seen.append(binding.active()))
        other.start()
        other.join()
    assert seen == [None]


def test_an_attempt_recognizes_only_the_conflicts_its_execution_handed_it() -> None:
    lifetime = TxnAttemptLifetime()
    assert lifetime.recognized_conflicts == ()
    conflict = RuntimeError("an exclusion violation")
    lifetime.recognize_conflict(conflict)
    assert tuple(lifetime.recognized_conflicts) == (conflict,)
