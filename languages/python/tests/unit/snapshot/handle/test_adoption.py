"""The adoption seam every root execution runs through (spec §3, Docker-free).

`AdoptedExecution` owns two things: which selection an execution runs under
from the moment it adopts, and the one `except` clause that turns an ordinary
failure escaping the execution into an `ExecutionFailure` naming that edition.
This grades the wrap matrix directly — what is wrapped, what passes through
unchanged, and which edition a failure reports when the execution adopted more
than once — so the demarcation suite can grade `db.transact` against the seam
rather than restate it.
"""

from __future__ import annotations

from typing import NoReturn

import pytest

from parallax.snapshot import ExecutionFailure, ServingModel, prepare_model
from parallax.snapshot.handle._adoption import AdoptedExecution
from tests.unit._transact_support import ACCOUNT

_A = prepare_model(ACCOUNT, edition="a")
_B = prepare_model(ACCOUNT, edition="b")


def _serving() -> ServingModel:
    return ServingModel(_A)


def test_adopt_takes_the_selection_currently_serving_and_edition_follows_it() -> None:
    serving = _serving()
    execution = AdoptedExecution(serving)

    assert execution.adopt() is _A
    assert execution.edition == "a"
    serving.publish(_B, expected=_A)
    # Retained until the next adoption: a publication changes nothing already
    # adopted, and adopting again takes what is serving now.
    assert execution.edition == "a"
    assert execution.adopt() is _B
    assert execution.edition == "b"


def test_edition_before_the_first_adoption_is_a_programming_error() -> None:
    execution = AdoptedExecution(_serving())
    with pytest.raises(RuntimeError, match="before it has adopted"):
        _ = execution.edition


def test_a_value_is_answered_unwrapped() -> None:
    execution = AdoptedExecution(_serving())
    execution.adopt()
    assert execution.contextualized(lambda: 42) == 42


def test_an_ordinary_failure_is_contextualized_under_the_adopted_edition() -> None:
    execution = AdoptedExecution(_serving())
    execution.adopt()
    cause = ValueError("boom")

    def body() -> NoReturn:
        raise cause

    with pytest.raises(ExecutionFailure) as failed:
        execution.contextualized(body)
    failure = failed.value
    assert failure.edition == "a"
    assert failure.cause is cause
    # Native chaining reads the same object the attribute answers.
    assert failure.__cause__ is cause
    assert "'a'" in str(failure)
    assert "boom" in str(failure)


def test_the_failure_names_the_edition_adopted_last() -> None:
    # A transaction adopts once per attempt and wraps once around the loop, so
    # the edition a failure reports is the one the last attempt ran under.
    serving = _serving()
    execution = AdoptedExecution(serving)

    def two_attempts() -> NoReturn:
        execution.adopt()
        serving.publish(_B, expected=_A)
        execution.adopt()
        raise ValueError("the second attempt failed")

    with pytest.raises(ExecutionFailure) as failed:
        execution.contextualized(two_attempts)
    assert failed.value.edition == "b"


def test_a_failure_already_contextualized_passes_through_unchanged() -> None:
    # A nested execution named its own edition; the outer one adds no second
    # wrapper, so what escapes still names the edition of the execution that
    # failed rather than the one that merely enclosed it.
    execution = AdoptedExecution(_serving())
    execution.adopt()
    inner = ExecutionFailure("other", ValueError("nested"))

    def body() -> NoReturn:
        raise inner

    with pytest.raises(ExecutionFailure) as failed:
        execution.contextualized(body)
    assert failed.value is inner
    assert failed.value.edition == "other"


@pytest.mark.parametrize("fatal", [KeyboardInterrupt, SystemExit, GeneratorExit])
def test_a_control_flow_or_fatal_exception_passes_through_untouched(
    fatal: type[BaseException],
) -> None:
    execution = AdoptedExecution(_serving())
    execution.adopt()
    raised = fatal()

    def body() -> NoReturn:
        raise raised

    with pytest.raises(fatal) as escaped:
        execution.contextualized(body)
    assert escaped.value is raised
    assert escaped.value.__cause__ is None


def test_an_execution_failure_exposes_its_two_facts_read_only() -> None:
    cause = RuntimeError("why")
    failure = ExecutionFailure("edition-x", cause)
    assert (failure.edition, failure.cause) == ("edition-x", cause)
    assert isinstance(failure, Exception)
    assert not isinstance(failure, RuntimeError)
    # What the failure reports is what it was raised with: a handler holding it
    # can neither restate the edition the execution ran under nor swap the
    # error that escaped it.
    for name in ("edition", "cause"):
        with pytest.raises(AttributeError):
            setattr(failure, name, ValueError("substituted"))
        with pytest.raises(AttributeError):
            delattr(failure, name)
    assert (failure.edition, failure.cause) == ("edition-x", cause)


def test_an_execution_failure_leaves_interpreter_owned_state_writable() -> None:
    # Read-only is about the two facts this failure reports, not about the
    # machinery every exception carries: chaining and notes still work.
    failure = ExecutionFailure("edition-x", RuntimeError("why"))
    replacement = ValueError("chaining stays interpreter-owned")
    failure.__cause__ = replacement
    failure.add_note("annotated")
    assert failure.__cause__ is replacement
    assert failure.__notes__ == ["annotated"]
