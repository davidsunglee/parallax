"""One installed Provider against real Postgres (m-execution-lifecycle,
m-api-conformance).

The Docker-free suites drive the seam over fake ports, where the row counts and
the durations are whatever the fake said. What only a real database can show is
that the two facts the events carry about it are its own: the physical row count
a query returned, and a monotonic duration around a round trip that actually
happened.

The decline is here for the opposite reason — it must be observable nowhere at
all. A Provider that answers ``None`` is asked once and told nothing after, and
the query it declined is the query an unobserved caller would have run.

The joined story is the Usage Guide's own source, executed here so the
documented spelling of the composition seam cannot drift from a working one.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from _support.corpus import case_fixtures
from parallax.conformance import case_format, engine, execution_lifecycle_stories
from parallax.conformance.class_models import MODELS
from parallax.conformance.story_models import Account
from parallax.core.execution_lifecycle import (
    DatabaseCallFinished,
    DatabaseCallStarted,
    DatabaseReadCompleted,
    ExecutionLifecycleHandler,
    ExecutionLifecycleHandlerError,
    ReadCompleted,
    ReadFinished,
    ReadStarted,
    RootExecution,
)
from parallax.core.execution_lifecycle.testing import RecordingLifecycleProvider
from parallax.snapshot import connect

_CASE_ID = "m-execution-lifecycle-001"


def _seeded(provisioner: Any) -> Any:
    case = next(case for case in case_format.load_cases() if case.case_id == _CASE_ID)
    provisioner.reset(engine.load_case_metamodel(case), case_fixtures(case))
    return provisioner.port


class _Declining:
    """A Provider that declines every root and records what it was asked."""

    def __init__(self) -> None:
        self.opened: list[RootExecution] = []
        self.reported: list[ExecutionLifecycleHandlerError] = []

    def open(self, execution: RootExecution, /) -> ExecutionLifecycleHandler | None:
        self.opened.append(execution)
        return None

    def report_handler_error(self, error: ExecutionLifecycleHandlerError, /) -> None:
        self.reported.append(error)


def test_a_provider_observes_one_read_root_against_a_real_database(provisioner: Any) -> None:
    recorder = RecordingLifecycleProvider()
    db = connect(_seeded(provisioner), MODELS["account"], lifecycle_provider=recorder)

    account = db.find(Account.where(Account.id == 2)).result()
    assert account.balance == Decimal("250.00")

    (root,) = recorder.roots
    assert root.execution.kind == "READ"
    started, call_started, call_finished, finished = root.events
    assert isinstance(started, ReadStarted)
    assert started.interface == "TYPED"
    assert isinstance(call_started, DatabaseCallStarted)
    assert call_started.kind == "READ"
    assert isinstance(call_finished, DatabaseCallFinished)
    # The row count is the driver's own, and the duration brackets a round trip
    # that genuinely happened.
    assert call_finished.outcome == DatabaseReadCompleted(1)
    assert call_finished.duration_ns > 0
    assert isinstance(finished, ReadFinished)
    assert finished.outcome == ReadCompleted()

    # Nothing the read answered carries a lifecycle accessor: the stream above
    # is the whole record, and it was delivered rather than retained.
    assert not hasattr(account, "execution")


def test_two_reads_through_one_handle_are_two_independent_roots(provisioner: Any) -> None:
    recorder = RecordingLifecycleProvider()
    db = connect(_seeded(provisioner), MODELS["account"], lifecycle_provider=recorder)
    db.find(Account.where(Account.id == 2)).result()
    db.find(Account.where(Account.id == 2)).result()

    first, second = recorder.roots
    assert first.execution.id != second.execution.id
    # Independent sequences: the second root starts over at one rather than
    # continuing the first, and neither implies an order over the other.
    assert [event.sequence for event in first.events] == [1, 2, 3, 4]
    assert [event.sequence for event in second.events] == [1, 2, 3, 4]


def test_a_declining_provider_changes_nothing_about_the_query(provisioner: Any) -> None:
    provider = _Declining()
    db = connect(_seeded(provisioner), MODELS["account"], lifecycle_provider=provider)

    assert db.find(Account.where(Account.id == 2)).result().balance == Decimal("250.00")
    assert [execution.kind for execution in provider.opened] == ["READ"]
    assert provider.reported == []


def test_the_joined_usage_guide_story_runs_against_a_real_database(provisioner: Any) -> None:
    shape = execution_lifecycle_stories.a_joined_unit_of_work_is_observed_inside_the_outer_attempt(
        _seeded(provisioner), MODELS["account"]
    )
    # One outermost operation is one root, however many joined calls it makes,
    # and a joined call runs no attempt of its own.
    assert shape.roots == 1
    assert shape.attempts == 1
    assert shape.joined_parent_is_the_attempt
    assert shape.balance == Decimal("251.00")
