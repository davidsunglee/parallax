"""Several Providers behind one seam, and the isolation between them
(m-execution-lifecycle, Docker-free).

``connect`` takes one Provider, so composing several is the fan-out's job rather
than the publisher's. What that buys has to be graded as ISOLATION: children see
one shared event in declaration order, a child that fails ordinarily loses the
rest of its root alone, and the siblings after it in the same delivery still
receive the event it failed on.

Both halves are driven here — the composition through ``connect`` where a real
application installs it, and the ordering and quarantine rules against the
fan-out itself, where the sequence of children is the thing being asserted.
"""

from __future__ import annotations

import io
from typing import Any
from uuid import uuid4

import pytest
from _transact_support import ACCOUNT, FIXED, NEW_ROW, RecordingPort

from _support import mirrored_models as mm
from parallax.core.execution_lifecycle import (
    ExecutionEvent,
    ExecutionLifecycleHandler,
    ExecutionLifecycleHandlerError,
    ExecutionLifecycleProviderError,
    FanoutLifecycleProvider,
    ReadStarted,
    RootExecution,
)
from parallax.core.execution_lifecycle._diagnostics import diagnostic_for
from parallax.core.unit_work import FixedClock
from parallax.snapshot import connect
from parallax.snapshot.handle import Database

READ = RootExecution(uuid4(), "READ")
STARTED = ReadStarted(READ.id, 1, 1, None, "Account", "TYPED")
NEXT = ReadStarted(READ.id, 2, 2, 1, "Account", "TYPED")


class _Child:
    """One composed Provider, recording what its Handler saw and what it was told.

    ``fail_at`` makes the Handler raise ordinarily on that event ordinal, which
    is the failure the fan-out is required to contain to this child alone.
    """

    def __init__(
        self,
        name: str,
        *,
        declines: bool = False,
        opening_failure: BaseException | None = None,
        fail_at: int | None = None,
        failure: BaseException | None = None,
    ) -> None:
        self.name = name
        self._declines = declines
        self._opening_failure = opening_failure
        self._fail_at = fail_at
        self._failure = failure if failure is not None else RuntimeError(f"{name} is full")
        self.opened: list[RootExecution] = []
        self.handlers: list[_ChildHandler] = []
        self.reported: list[ExecutionLifecycleHandlerError] = []

    def open(self, execution: RootExecution, /) -> ExecutionLifecycleHandler | None:
        self.opened.append(execution)
        if self._opening_failure is not None:
            raise self._opening_failure
        if self._declines:
            return None
        handler = _ChildHandler(self._fail_at, self._failure)
        self.handlers.append(handler)
        return handler

    def report_handler_error(self, error: ExecutionLifecycleHandlerError, /) -> None:
        self.reported.append(error)

    @property
    def seen(self) -> list[ExecutionEvent]:
        return [] if not self.handlers else self.handlers[0].seen


class _ChildHandler:
    def __init__(self, fail_at: int | None, failure: BaseException) -> None:
        self._fail_at = fail_at
        self._failure = failure
        self.seen: list[ExecutionEvent] = []

    def handle(self, event: ExecutionEvent, /) -> None:
        self.seen.append(event)
        if len(self.seen) == self._fail_at:
            raise self._failure


def _handler(*children: Any) -> ExecutionLifecycleHandler:
    opened = FanoutLifecycleProvider(children).open(READ)
    assert opened is not None
    return opened


def _db(port: RecordingPort, provider: Any) -> Database:
    return connect(port, ACCOUNT, clock=FixedClock(FIXED), lifecycle_provider=provider)


def test_an_empty_fan_out_is_refused_at_construction() -> None:
    with pytest.raises(ValueError, match="at least one provider"):
        FanoutLifecycleProvider(())


def test_composing_one_provider_object_twice_is_refused_at_construction() -> None:
    child = _Child("metrics")
    with pytest.raises(ValueError, match="at most once"):
        FanoutLifecycleProvider([child, _Child("tracing"), child])


def test_composing_one_provider_object_inside_a_nested_fan_out_is_refused() -> None:
    # A nested fan-out contributes its children to the SAME composition tree, so
    # a leaf reached down two branches is opened twice for one root and its
    # Handler sees every event twice — the cost the repeat rule refuses.
    child = _Child("metrics")
    with pytest.raises(ValueError, match="at most once") as refused:
        FanoutLifecycleProvider([child, FanoutLifecycleProvider([child])])
    assert "position 1.0 is already composed at 0" in str(refused.value)


def test_two_nested_fan_outs_sharing_one_leaf_are_refused() -> None:
    child = _Child("metrics")
    with pytest.raises(ValueError, match="at most once"):
        FanoutLifecycleProvider(
            [
                FanoutLifecycleProvider([_Child("tracing"), child]),
                FanoutLifecycleProvider([child]),
            ]
        )


def test_two_distinct_providers_sharing_a_backend_are_accepted() -> None:
    # Deliberate sharing is how one exporter is fed under two configurations,
    # and the rule is about the OBJECT rather than about what it writes to.
    backend: list[str] = []

    class _Sharing(_Child):
        def report_handler_error(self, error: ExecutionLifecycleHandlerError, /) -> None:
            backend.append(self.name)
            super().report_handler_error(error)

    first, second = _Sharing("safe"), _Sharing("diagnostic")
    _handler(first, second).handle(STARTED)
    assert [child.seen for child in (first, second)] == [[STARTED], [STARTED]]
    assert backend == []


def test_children_open_in_declaration_order_and_receive_one_shared_event() -> None:
    children = [_Child("first"), _Child("second"), _Child("third")]
    handler = _handler(*children)
    handler.handle(STARTED)
    assert [child.opened for child in children] == [[READ]] * 3
    # One object, not one per child: nothing is cloned for delivery, which is
    # what keeps a borrowed statement a single value.
    assert all(child.seen[0] is STARTED for child in children)


def test_a_fan_out_declines_only_when_every_child_declines() -> None:
    all_declining = [_Child("a", declines=True), _Child("b", declines=True)]
    assert FanoutLifecycleProvider(all_declining).open(READ) is None
    assert [child.opened for child in all_declining] == [[READ], [READ]]

    accepting = _Child("c")
    some = FanoutLifecycleProvider([_Child("a", declines=True), accepting])
    opened = some.open(READ)
    assert opened is not None
    opened.handle(STARTED)
    assert accepting.seen == [STARTED]


def test_a_child_opening_failure_aborts_the_root_and_discards_what_opened() -> None:
    first = _Child("first")
    failing = _Child("second", opening_failure=RuntimeError("the exporter is not configured"))
    later = _Child("third")
    port = RecordingPort(rows=[NEW_ROW])
    db = _db(port, FanoutLifecycleProvider([first, failing, later]))

    with pytest.raises(ExecutionLifecycleProviderError):
        db.find(mm.Account.where(mm.Account.id == 7)).result()
    # The handler the first child had already answered is discarded unused, and
    # the child after the failure is never asked at all.
    assert first.handlers[0].seen == []
    assert later.opened == []
    assert port.ops == []


def test_an_ordinarily_failing_child_is_quarantined_alone() -> None:
    before, failing, after = _Child("before"), _Child("failing", fail_at=1), _Child("after")
    handler = _handler(before, failing, after)
    handler.handle(STARTED)
    handler.handle(NEXT)

    # The sibling AFTER the failure still received the very event it failed on,
    # and both siblings keep receiving everything afterwards.
    assert before.seen == [STARTED, NEXT]
    assert after.seen == [STARTED, NEXT]
    assert failing.seen == [STARTED]


def test_two_children_failing_on_one_event_are_each_quarantined_alone() -> None:
    # The survivors of a delivery are collected in one pass, so the second
    # failure of the same event has to be dropped from a list the first already
    # started rather than from the one the delivery began with.
    first, second, third = (
        _Child("first", fail_at=1),
        _Child("second", fail_at=1),
        _Child("third"),
    )
    handler = _handler(first, second, third)
    handler.handle(STARTED)
    handler.handle(NEXT)

    assert first.seen == [STARTED]
    assert second.seen == [STARTED]
    assert third.seen == [STARTED, NEXT]
    assert [child.reported[0].fanout_path for child in (first, second)] == [(0,), (1,)]


def test_a_quarantined_child_is_reported_to_its_own_provider_with_its_position() -> None:
    before, failing = _Child("before"), _Child("failing", fail_at=1)
    _handler(before, failing).handle(STARTED)

    assert before.reported == []
    (reported,) = failing.reported
    assert reported.fanout_path == (1,)
    assert reported.execution_id == READ.id
    assert (reported.sequence, reported.activity_id) == (1, 1)
    assert reported.handler_type.endswith("._ChildHandler")
    assert reported.diagnostic.message == "failing is full"


def test_a_nested_fan_out_reports_the_whole_path_descended_to_reach_a_child() -> None:
    # The position of a Handler in the tree is known only by the fan-out above
    # it, so a nested child reporting its own last step alone would leave the
    # path unable to locate it.
    leaf = _Child("leaf", fail_at=1)
    inner = FanoutLifecycleProvider([_Child("sibling"), leaf])
    _handler(_Child("outer"), inner).handle(STARTED)

    (reported,) = leaf.reported
    assert reported.fanout_path == (1, 1)


def test_a_nested_fan_out_that_declines_wholly_is_skipped_by_its_parent() -> None:
    inner = FanoutLifecycleProvider([_Child("a", declines=True)])
    accepting = _Child("outer")
    _handler(accepting, inner).handle(STARTED)
    assert accepting.seen == [STARTED]


def test_a_fatal_child_failure_is_not_contained_by_the_fan_out() -> None:
    interrupt = KeyboardInterrupt()
    before = _Child("before")
    fatal = _Child("fatal", fail_at=1, failure=interrupt)
    after = _Child("after")
    with pytest.raises(KeyboardInterrupt) as escaped:
        _handler(before, fatal, after).handle(STARTED)
    assert escaped.value is interrupt
    # It aborts the whole root through the publisher above, so the sibling after
    # it never sees the event and no Handler Error is produced for anyone.
    assert after.seen == []
    assert fatal.reported == []


def test_a_childs_failing_reporter_costs_only_the_last_resort_line(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stderr = io.StringIO()
    monkeypatch.setattr("sys.__stderr__", stderr)

    class _FailingReporter(_Child):
        def report_handler_error(self, error: ExecutionLifecycleHandlerError, /) -> None:
            super().report_handler_error(error)
            raise RuntimeError("the reporter is unreachable")

    failing = _FailingReporter("failing", fail_at=1)
    after = _Child("after")
    _handler(failing, after).handle(STARTED)

    # Reporting a quarantine is best effort, so its own failure may not escape
    # into the delivery it was reporting on: the later sibling still got the
    # event, and one correlation-only line records the dropped report.
    assert after.seen == [STARTED]
    assert "sequence=1 activity=1" in stderr.getvalue()


def test_a_report_about_the_composite_itself_reaches_every_composed_provider() -> None:
    # The composite belongs to all of the children and to none of them: it
    # contains each child's own ordinary failure, so a report arriving at the
    # fan-out describes the object whose loss costs every child the rest of the
    # root, and telling each of them is what keeps that from being silent.
    children = [_Child("first"), _Child("second")]
    error = ExecutionLifecycleHandlerError(
        execution_id=READ.id,
        sequence=1,
        activity_id=1,
        handler_type="tests._Composite",
        fanout_path=(),
        diagnostic=diagnostic_for(RuntimeError("the composite itself failed")),
    )
    FanoutLifecycleProvider(children).report_handler_error(error)
    assert [child.reported for child in children] == [[error], [error]]


def test_a_fan_out_installed_through_connect_observes_a_whole_read() -> None:
    children = [_Child("metrics"), _Child("tracing")]
    port = RecordingPort(rows=[NEW_ROW])
    db = _db(port, FanoutLifecycleProvider(children))
    db.find(mm.Account.where(mm.Account.id == 7)).result()

    transitions = [type(event).__name__ for event in children[0].seen]
    assert transitions == [
        "ReadStarted",
        "DatabaseCallStarted",
        "DatabaseCallFinished",
        "ReadFinished",
    ]
    assert children[1].seen == children[0].seen
