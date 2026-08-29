"""The Usage Guide's lifecycle story, over a fake port.

The story is documentation that runs: its source IS the guide's snippet, and
`tests/api/test_execution_lifecycle_story.py` executes it against real Postgres
so what is documented is what works. This is the database-free half — the same
call over a scripted port — because a snippet that stopped compiling, or a
Provider that stopped being asked, should fail on the first run of the fast
suite rather than on the Docker-backed one.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from decimal import Decimal
from uuid import uuid4

import pytest

from _support.db_port import body_outcome
from parallax.conformance import execution_lifecycle_stories
from parallax.conformance.class_models import MODELS
from parallax.core.db_port import Bind, DbPort, Row, TransactionOutcome
from parallax.core.dialect import POSTGRES, Dialect
from parallax.core.execution_lifecycle import (
    ExecutionLifecycleHandlerError,
    FailureDiagnostic,
    RootExecution,
)


class _AccountPort:
    """The one seeded row the story bumps, and a driver that accepts the write."""

    dialect: Dialect = POSTGRES

    def __init__(self) -> None:
        self.writes: list[str] = []

    def execute(
        self, sql: str, binds: Sequence[Bind], document_reads: Sequence[object] = ()
    ) -> list[Row]:
        return [{"id": 2, "owner": "Linus", "balance": Decimal("250.00"), "version": 1}]

    def execute_write(self, sql: str, binds: Sequence[Bind]) -> int:
        self.writes.append(sql)
        return 1

    def transaction[T](
        self, body: Callable[[DbPort], T], *, isolation: str | None = None
    ) -> TransactionOutcome[T]:
        return body_outcome(self, body)


def test_the_documented_joined_story_observes_one_root_and_one_attempt() -> None:
    port = _AccountPort()
    shape = execution_lifecycle_stories.a_joined_unit_of_work_is_observed_inside_the_outer_attempt(
        port, MODELS["account"]
    )
    # One outermost operation is one Root Execution however many joined calls it
    # makes, and a joined call creates no Transaction Attempt of its own.
    assert shape.roots == 1
    assert shape.attempts == 1
    assert shape.joined_parent_is_the_attempt
    assert shape.balance == Decimal("251.00")
    # The joined body's write reached the database under the OUTER boundary.
    assert len(port.writes) == 1


def test_the_snippet_the_usage_guide_renders_is_the_source_that_ran() -> None:
    snippet = execution_lifecycle_stories.joined_lifecycle_snippet()
    # The Handler, the Provider, and the call are one story: a snippet showing
    # the call alone would document the seam without what sits behind it.
    assert "class JoinedShapeHandler" in snippet
    assert "class JoinedShapeProvider" in snippet
    assert "lifecycle_provider=provider" in snippet


def test_the_storys_provider_refuses_to_swallow_a_handler_failure() -> None:
    # A Provider is told about an ordinary Handler failure out of band, and it
    # never changes the execution it was observing — which is exactly why a
    # story whose Handler cannot fail treats being told as its own defect
    # rather than as something to log and move past.
    provider = execution_lifecycle_stories.JoinedShapeProvider()
    assert provider.open(RootExecution(uuid4(), "READ")) is not None
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
