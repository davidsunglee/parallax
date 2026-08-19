"""Provider opening, Handler containment, and last-resort reporting
(m-execution-lifecycle, Docker-free).

Delivery is where a badly behaved application meets a running query, and the
whole point of the contract is that the query does not notice. The layers differ
in blast radius, so each is proven against what it is allowed to change: opening
may refuse the operation because nothing has begun, an ordinary Handler failure
may cost only that Handler, and a control-flow or fatal exception may abort the
root while propagating unchanged.

Driven through :meth:`Database.find` over a fake port rather than against the
publisher directly: the seam an application installs is ``connect``'s own
argument, so what is graded here is what an application would actually see.
"""

from __future__ import annotations

import io
from collections.abc import Sequence
from typing import Any
from uuid import uuid4

import pytest
from _transact_support import ACCOUNT, FIXED, NEW_ROW, RecordingPort, read_account

from _support import mirrored_models as mm
from parallax.core.db_error import DatabaseError
from parallax.core.db_port import Bind, Row
from parallax.core.execution_lifecycle import (
    DatabaseCallFinished,
    DatabaseFailureDiagnostic,
    DatabaseWriteCompleted,
    ExecutionEvent,
    ExecutionLifecycleHandler,
    ExecutionLifecycleHandlerError,
    ExecutionLifecycleProviderError,
    FailureDiagnostic,
    ReadStarted,
    RootExecution,
    _activity,
)
from parallax.core.execution_lifecycle._activity import (
    DeliveryState,
    InstalledLifecycle,
    open_read_root,
)
from parallax.core.execution_lifecycle._diagnostics import (
    database_diagnostic_for,
    diagnostic_for,
)
from parallax.core.execution_lifecycle.testing import RecordingLifecycleProvider
from parallax.core.metamodel import EntityIdentity
from parallax.core.sql_gen import LoweredStatement
from parallax.core.unit_work import FixedClock
from parallax.snapshot import connect
from parallax.snapshot.handle import Database


def _db(port: RecordingPort, provider: Any) -> Database:
    return connect(port, ACCOUNT, clock=FixedClock(FIXED), lifecycle_provider=provider)


def _installed(provider: Any) -> InstalledLifecycle:
    """What a handle holds for ``provider`` — the seam below ``connect`` takes.

    Spelled out only where a suite drives the root opener or the publisher
    directly rather than going through a handle, which is the one place the
    pairing is not made for it.
    """
    return InstalledLifecycle(provider, DeliveryState())


def _read(db: Database) -> None:
    db.find(mm.Account.where(mm.Account.id == 7)).result()


class _Declining:
    """A Provider that declines every root and is told about nothing after."""

    def __init__(self) -> None:
        self.opened: list[RootExecution] = []
        self.reported: list[ExecutionLifecycleHandlerError] = []

    def open(self, execution: RootExecution, /) -> ExecutionLifecycleHandler | None:
        self.opened.append(execution)
        return None

    def report_handler_error(self, error: ExecutionLifecycleHandlerError, /) -> None:
        self.reported.append(error)


class _RaisingOpen:
    """A Provider whose opening fails ordinarily."""

    def __init__(self, failure: BaseException) -> None:
        self._failure = failure

    def open(self, execution: RootExecution, /) -> ExecutionLifecycleHandler | None:
        del execution
        raise self._failure

    def report_handler_error(self, error: ExecutionLifecycleHandlerError, /) -> None:
        raise AssertionError("a provider that never opened is told about no handler")


class _FailingHandler:
    """A Handler that raises on the nth event it is given, then records."""

    def __init__(self, fail_at: int, failure: BaseException) -> None:
        self._fail_at = fail_at
        self._failure = failure
        self.seen: list[ExecutionEvent] = []

    def handle(self, event: ExecutionEvent, /) -> None:
        self.seen.append(event)
        if len(self.seen) == self._fail_at:
            raise self._failure


class _NamelessMeta(type):
    def __getattribute__(cls, name: str) -> Any:
        if name == "__qualname__":
            raise RuntimeError("this handler type refuses to name itself")
        return super().__getattribute__(name)


class _NamelessHandler(metaclass=_NamelessMeta):
    """A Handler whose own type cannot be named, and which fails ordinarily."""

    def handle(self, event: ExecutionEvent, /) -> None:
        del event
        raise RuntimeError("the exporter queue is full")


class _FailingReadPort(RecordingPort):
    """A port whose query call comes back with a classified failure."""

    def execute(
        self, sql: str, binds: Sequence[Bind], document_reads: Sequence[tuple[int, int]] = ()
    ) -> list[Row]:
        del sql, binds, document_reads
        raise DatabaseError(
            category="lockWaitTimeout", native_code="55P03", message="lock wait timeout"
        )


class _Provider:
    """A Provider answering one prepared Handler and recording its reports."""

    def __init__(self, handler: Any, *, reporting_failure: BaseException | None = None) -> None:
        self._handler = handler
        self._reporting_failure = reporting_failure
        self.reported: list[ExecutionLifecycleHandlerError] = []

    def open(self, execution: RootExecution, /) -> ExecutionLifecycleHandler | None:
        del execution
        return self._handler

    def report_handler_error(self, error: ExecutionLifecycleHandlerError, /) -> None:
        self.reported.append(error)
        if self._reporting_failure is not None:
            raise self._reporting_failure


def test_an_accepted_root_carries_a_uuid4_descriptor_of_its_own_kind() -> None:
    handler = _FailingHandler(fail_at=0, failure=RuntimeError())
    provider = _Provider(handler)
    port = RecordingPort(rows=[NEW_ROW])
    _read(_db(port, provider))
    started = handler.seen[0]
    assert isinstance(started, ReadStarted)
    assert started.execution_id.version == 4
    assert (started.sequence, started.activity_id, started.parent_activity_id) == (1, 1, None)


def test_two_operations_are_two_roots_with_independent_sequences() -> None:
    handler_a = _FailingHandler(fail_at=0, failure=RuntimeError())
    handler_b = _FailingHandler(fail_at=0, failure=RuntimeError())
    handlers = [handler_a, handler_b]

    class _PerRoot:
        def __init__(self) -> None:
            self.opened: list[RootExecution] = []

        def open(self, execution: RootExecution, /) -> ExecutionLifecycleHandler | None:
            self.opened.append(execution)
            return handlers[len(self.opened) - 1]

        def report_handler_error(self, error: ExecutionLifecycleHandlerError, /) -> None:
            raise AssertionError("no handler failed")

    provider = _PerRoot()
    port = RecordingPort(rows=[NEW_ROW])
    db = _db(port, provider)
    _read(db)
    _read(db)
    ids = [execution.id for execution in provider.opened]
    assert len(set(ids)) == 2
    assert [event.execution_id for event in handler_a.seen] == [ids[0]] * len(handler_a.seen)
    assert [event.sequence for event in handler_a.seen] == [
        event.sequence for event in handler_b.seen
    ]


def test_a_declining_provider_is_asked_once_and_told_nothing_after() -> None:
    provider = _Declining()
    port = RecordingPort(rows=[NEW_ROW])
    db = _db(port, provider)
    _read(db)
    assert [execution.kind for execution in provider.opened] == ["READ"]
    assert provider.reported == []
    # The declined root ran the query exactly as an unobserved one does.
    assert [op[0] for op in port.ops] == ["read"]


def test_an_ordinary_opening_failure_refuses_the_operation_before_any_work() -> None:
    cause = RuntimeError("the exporter is not configured")
    port = RecordingPort(rows=[NEW_ROW])
    db = _db(port, _RaisingOpen(cause))
    with pytest.raises(ExecutionLifecycleProviderError) as refusal:
        _read(db)
    assert refusal.value.__cause__ is cause
    assert port.ops == [], "the refusal precedes every database call"


def test_a_control_flow_exception_from_opening_propagates_unchanged() -> None:
    interrupt = KeyboardInterrupt()
    port = RecordingPort(rows=[NEW_ROW])
    db = _db(port, _RaisingOpen(interrupt))
    with pytest.raises(KeyboardInterrupt) as escaped:
        _read(db)
    assert escaped.value is interrupt
    assert port.ops == []


def test_an_ordinary_handler_failure_quarantines_only_that_handler() -> None:
    failure = RuntimeError("the exporter queue is full")
    handler = _FailingHandler(fail_at=1, failure=failure)
    provider = _Provider(handler)
    port = RecordingPort(rows=[NEW_ROW])
    assert _db(port, provider).find(mm.Account.where(mm.Account.id == 7)).result() == read_account()

    # The query is unchanged; the Handler saw its first event and no later one.
    assert len(handler.seen) == 1
    (reported,) = provider.reported
    assert reported.sequence == 1
    assert reported.activity_id == 1
    assert reported.fanout_path == ()
    assert reported.handler_type.endswith("._FailingHandler")
    assert reported.diagnostic.message == "the exporter queue is full"
    assert reported.execution_id == handler.seen[0].execution_id


def test_a_handler_error_carries_no_event_statement_or_bind() -> None:
    handler = _FailingHandler(fail_at=2, failure=RuntimeError("boom"))
    provider = _Provider(handler)
    port = RecordingPort(rows=[NEW_ROW])
    _read(_db(port, provider))
    (reported,) = provider.reported
    assert set(type(reported).__dataclass_fields__) == {
        "execution_id",
        "sequence",
        "activity_id",
        "handler_type",
        "fanout_path",
        "diagnostic",
    }
    # The failing event was the Database Call's Started, whose statement is
    # borrowed for delivery alone; nothing about it survives the report.
    assert "select" not in repr(reported).lower()


def test_a_failing_reporter_writes_one_correlation_only_line_and_stops(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stderr = io.StringIO()
    monkeypatch.setattr("sys.__stderr__", stderr)
    handler = _FailingHandler(fail_at=1, failure=RuntimeError("the exporter queue is full"))
    provider = _Provider(handler, reporting_failure=RuntimeError("the reporter is unreachable"))
    port = RecordingPort(rows=[NEW_ROW])
    _read(_db(port, provider))
    line = stderr.getvalue()
    assert line.count("\n") == 1
    assert "sequence=1 activity=1" in line
    # Correlation only: neither failure's own message reaches the stream, and
    # nothing about the event that was being delivered does either.
    assert "queue" not in line and "unreachable" not in line


def test_the_last_resort_path_is_dropped_silently_when_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("sys.__stderr__", None)
    handler = _FailingHandler(fail_at=1, failure=RuntimeError("handler"))
    provider = _Provider(handler, reporting_failure=RuntimeError("reporter"))
    port = RecordingPort(rows=[NEW_ROW])
    assert _read(_db(port, provider)) is None


def test_a_closed_last_resort_stream_is_dropped_silently(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stream = io.StringIO()
    stream.close()
    monkeypatch.setattr("sys.__stderr__", stream)
    handler = _FailingHandler(fail_at=1, failure=RuntimeError("handler"))
    provider = _Provider(handler, reporting_failure=RuntimeError("reporter"))
    port = RecordingPort(rows=[NEW_ROW])
    assert _read(_db(port, provider)) is None


def test_a_base_exception_from_delivery_aborts_the_root_and_propagates_unchanged() -> None:
    interrupt = KeyboardInterrupt()
    handler = _FailingHandler(fail_at=1, failure=interrupt)
    provider = _Provider(handler)
    port = RecordingPort(rows=[NEW_ROW])
    with pytest.raises(KeyboardInterrupt) as escaped:
        _read(_db(port, provider))
    assert escaped.value is interrupt
    # No Handler Error is produced, and delivery for the root is deactivated —
    # the Read's own Finished never reaches the quarantined Handler.
    assert provider.reported == []
    assert len(handler.seen) == 1


def test_a_handler_type_that_refuses_to_name_itself_costs_only_its_name() -> None:
    # The quarantine report names the Handler's qualified type, which is read off
    # a type this module does not own: a metaclass may make either half of that
    # name raise. Extracting it is contained like every other projected field, so
    # an ordinary Handler failure still quarantines only that Handler.
    handler = _NamelessHandler()
    provider = _Provider(handler)
    port = RecordingPort(rows=[NEW_ROW])
    assert _db(port, provider).find(mm.Account.where(mm.Account.id == 7)).result() == read_account()
    (reported,) = provider.reported
    assert reported.handler_type == "<unavailable>"
    assert reported.diagnostic.message == "the exporter queue is full"


def test_cleanup_after_a_fatal_deactivation_renders_no_diagnostic(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # "Aborts and cleans up WITHOUT further events" is a claim about the work,
    # not only about delivery: a scope that still built its Finished event would
    # render a whole traceback per enclosing level for an event nobody will ever
    # receive. The scopes ask the publisher whether it is still active first.
    rendered: list[str] = []

    def counting(exc: BaseException) -> FailureDiagnostic:
        rendered.append(type(exc).__name__)
        return diagnostic_for(exc)

    monkeypatch.setattr(_activity, "diagnostic_for", counting)
    interrupt = KeyboardInterrupt()
    provider = _Provider(_FailingHandler(fail_at=2, failure=interrupt))
    port = RecordingPort(rows=[NEW_ROW])
    with pytest.raises(KeyboardInterrupt) as escaped:
        _read(_db(port, provider))
    assert escaped.value is interrupt
    assert rendered == []


def test_a_quarantined_root_renders_no_diagnostic_for_a_failed_call(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # The same guard under an ordinary quarantine: the Handler is gone for the
    # rest of the root, so a failed Database Call after it neither classifies its
    # own failure nor attributes it — while the failure itself is untouched.
    rendered: list[str] = []

    def counting(exc: BaseException) -> DatabaseFailureDiagnostic:
        rendered.append(type(exc).__name__)
        return database_diagnostic_for(exc)

    monkeypatch.setattr(_activity, "database_diagnostic_for", counting)
    provider = _Provider(_FailingHandler(fail_at=2, failure=RuntimeError("queue full")))
    port = _FailingReadPort()
    with pytest.raises(DatabaseError):
        _read(_db(port, provider))
    assert rendered == []
    (reported,) = provider.reported
    assert reported.diagnostic.message == "queue full"


def test_a_deactivated_publisher_drops_an_event_it_is_still_handed() -> None:
    # Containment lives in the publisher, and the activity guard above it only
    # saves the work of building what would be dropped. Delivery is driven here
    # directly so a future activity that forgets to ask cannot revive a root.
    handler = _FailingHandler(fail_at=1, failure=KeyboardInterrupt())
    provider = _Provider(handler)
    execution = RootExecution(uuid4(), "READ")
    publisher = _activity._Publisher(  # pyright: ignore[reportPrivateUsage] - the unit test drives the per-root publisher directly
        execution.id, _installed(provider), handler
    )
    event = ReadStarted(execution.id, 1, 1, None, "Account", "TYPED")
    with pytest.raises(KeyboardInterrupt):
        publisher.deliver(event)
    assert not publisher.active
    publisher.deliver(event)
    assert len(handler.seen) == 1
    assert provider.reported == []


def test_the_recorder_groups_its_roots_and_keeps_what_it_is_told() -> None:
    # The testing-only complete recorder: a suite grading a delivered stream
    # needs the whole stream, so it keeps every event of every root it accepted
    # and every Handler failure it was told about — the two things a production
    # observability path must not do.
    recorder = RecordingLifecycleProvider()
    port = RecordingPort(rows=[NEW_ROW])
    db = _db(port, recorder)
    _read(db)
    _read(db)

    first, second = recorder.roots
    assert first.execution.id != second.execution.id
    assert [event.sequence for event in first.events] == [1, 2, 3, 4]
    assert recorder.handler_errors == ()

    reported = ExecutionLifecycleHandlerError(
        execution_id=first.execution.id,
        sequence=1,
        activity_id=1,
        handler_type="tests._Handler",
        fanout_path=(),
        diagnostic=diagnostic_for(RuntimeError("boom")),
    )
    recorder.report_handler_error(reported)
    assert recorder.handler_errors == (reported,)


def test_a_database_call_reports_a_write_count_the_same_way_it_reports_a_read() -> None:
    # The Write Batch that opens one lands with the transaction emitters, so the
    # scope's write completion is driven here directly: a call announces only the
    # count its body knows, and which count that is decides the outcome.
    recorder = RecordingLifecycleProvider()
    account = EntityIdentity(None, "Account")
    root = open_read_root(_installed(recorder), target=account, interface="TYPED")
    statement = LoweredStatement("update account set balance = ?", (5,))
    with root as read, read.database_call(statement, "WRITE", account) as call:
        call.write_completed(3)

    (recorded,) = recorder.roots
    finished = recorded.events[2]
    assert isinstance(finished, DatabaseCallFinished)
    assert finished.outcome == DatabaseWriteCompleted(3)
    assert finished.statement is statement
