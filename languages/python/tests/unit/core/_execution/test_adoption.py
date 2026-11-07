"""The adoption seam every root execution runs through (`execution.md`, Docker-free).

The wrap matrix is graded where a failure escapes, in the runner and read-pipeline
suites; what stays here is what no execution reaches: reading an edition before
any adoption, and what an `ExecutionFailure` holder may and may not write.
"""

from __future__ import annotations

import pytest

from parallax.conformance.class_models import MODELS
from parallax.core._execution._adoption import AdoptedExecution
from parallax.core.execution import (
    ExecutionFailure,
    ServingModel,
    prepare_model,
)

_A = prepare_model(MODELS["account"], edition="a")


def _serving() -> ServingModel:
    return ServingModel(_A)


def test_edition_before_the_first_adoption_is_a_programming_error() -> None:
    execution = AdoptedExecution(_serving())
    with pytest.raises(RuntimeError, match="before it has adopted"):
        _ = execution.edition


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
