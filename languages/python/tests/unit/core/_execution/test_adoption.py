"""The adoption seam every root execution runs through (`execution.md`, Docker-free).

Which boundaries note a failure is graded where a failure escapes, in the runner
and read-pipeline suites; what stays here is the note itself: its text per
boundary, that it lands on the very object raised whatever its class, and what
it leaves alone.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import NoReturn

import pytest

from parallax.conformance.class_models import MODELS
from parallax.core import UsageError
from parallax.core._execution._adoption import AdoptedExecution, ExecutionBoundary
from parallax.core.execution import ServingModel, prepare_model
from parallax.core.read_delivery import InvalidDataError

_A = prepare_model(MODELS["account"], edition="a")


def _adopted() -> AdoptedExecution:
    execution = AdoptedExecution(ServingModel(_A))
    execution.adopt()
    return execution


def _raising(error: BaseException) -> Callable[[], NoReturn]:
    def body() -> NoReturn:
        raise error

    return body


def test_edition_before_the_first_adoption_is_a_programming_error() -> None:
    execution = AdoptedExecution(ServingModel(_A))
    with pytest.raises(RuntimeError, match="before it has adopted"):
        _ = execution.edition


def test_a_body_that_returns_is_answered_unchanged() -> None:
    assert _adopted().noting_edition("read", lambda: "answer") == "answer"


@pytest.mark.parametrize("boundary", ["transaction", "read", "stream"])
def test_the_note_names_the_boundary_and_the_adopted_edition(boundary: ExecutionBoundary) -> None:
    refusal = UsageError("stream-state-invalid", "a Parallax refusal")
    with pytest.raises(UsageError) as raised:
        _adopted().noting_edition(boundary, _raising(refusal))
    assert raised.value is refusal
    assert refusal.__notes__ == [f"raised in a {boundary} under model edition 'a'"]


def test_an_applications_own_exception_is_noted_and_keeps_its_identity_and_chain() -> None:
    origin = KeyError("what the callback was handling")
    own = LookupError("the application's own")
    own.__cause__ = origin
    with pytest.raises(LookupError) as raised:
        _adopted().noting_edition("transaction", _raising(own))
    assert raised.value is own
    assert own.__cause__ is origin
    assert own.__notes__ == ["raised in a transaction under model edition 'a'"]


def test_a_hand_frozen_stored_data_refusal_takes_the_note() -> None:
    refusal = InvalidDataError("stored-data-decoding-failed", "a stored value did not decode")
    with pytest.raises(InvalidDataError) as raised:
        _adopted().noting_edition("read", _raising(refusal))
    assert raised.value is refusal
    assert refusal.__notes__ == ["raised in a read under model edition 'a'"]


def test_each_boundary_a_failure_leaves_adds_its_own_note_innermost_first() -> None:
    inner = AdoptedExecution(ServingModel(prepare_model(MODELS["account"], edition="b")))
    inner.adopt()
    failure = RuntimeError("nested")
    with pytest.raises(RuntimeError):
        _adopted().noting_edition(
            "transaction", lambda: inner.noting_edition("read", _raising(failure))
        )
    assert failure.__notes__ == [
        "raised in a read under model edition 'b'",
        "raised in a transaction under model edition 'a'",
    ]


@pytest.mark.parametrize(
    "control",
    [KeyboardInterrupt(), SystemExit(1), GeneratorExit()],
    ids=["interrupt", "exit", "generator-exit"],
)
def test_control_flow_passes_through_unnoted(control: BaseException) -> None:
    with pytest.raises(type(control)) as raised:
        _adopted().noting_edition("transaction", _raising(control))
    assert raised.value is control
    assert not hasattr(control, "__notes__")
