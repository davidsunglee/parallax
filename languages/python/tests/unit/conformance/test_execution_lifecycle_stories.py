"""The Usage Guide lifecycle story's Provider, which treats a reported Handler
failure as its own defect."""

from __future__ import annotations

from uuid import uuid4

import pytest

from parallax.conformance import execution_lifecycle_stories
from parallax.core import ExecutionLifecycleHandlerError, RootExecution
from parallax.core.diagnostics import FailureDiagnostic


def test_the_storys_provider_refuses_to_swallow_a_handler_failure() -> None:
    # A Provider is told about an ordinary Handler failure out of band, and it
    # never changes the execution it was observing — which is exactly why a
    # story whose Handler cannot fail treats being told as its own defect
    # rather than as something to log and move past.
    provider = execution_lifecycle_stories.JoinedShapeProvider()
    assert provider.open(RootExecution(uuid4(), "read")) is not None
    reported = ExecutionLifecycleHandlerError(
        execution_id=uuid4(),
        sequence=1,
        activity_id=1,
        handler_type="tests.JoinedShapeHandler",
        fanout_path=(),
        diagnostic=FailureDiagnostic(
            qualified_type="builtins.ValueError",
            message="boom",
            code=None,
            stack="",
            message_truncated=False,
            stack_truncated=False,
        ),
    )
    with pytest.raises(AssertionError, match="must not fail"):
        provider.report_handler_error(reported)
