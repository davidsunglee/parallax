"""The Acquisition and Release activities (m-execution-lifecycle, Docker-free).

Resource observation is the one part of the lifecycle whose subject is not the
work but the CONNECTION the work ran on, and that difference is what this file
grades. Three claims run through it:

* **the shape** — an Acquisition and a Release are the owner's own first and
  last children, they contain nothing, a failed acquisition emits no Release,
  and inherited work emits neither;
* **the clocks** — the two durations bracket the resource calls alone, while
  the hold spans everything between them, delivery to the Handlers included;
* **the delivery** — resource handling is execution rather than observation, so
  a connection is taken and given back however badly the Handler above it
  behaves, and a cleanup fact reaches exactly one of a Handler and the
  restricted resource log.

Driven through `connect` over the scripted adapter, because the seam an
application installs is `connect`'s own argument and the thing under test is
what an application would see.
"""

from __future__ import annotations

import datetime as dt
import logging
from decimal import Decimal
from typing import Any, Final

import pytest
from _stream_page_support import paged_reads
from _transact_support import ACCOUNT, FIXED, NEW_ROW

from _support import mirrored_models as mm
from _support.adoption import raises_contextualized
from _support.db_port import (
    Read,
    ScriptedAdapter,
    ScriptedContext,
    Transact,
    Write,
)
from parallax.conformance.story_models import ORDERS_MODEL, Order
from parallax.core.db_error import DatabaseError
from parallax.core.db_port import (
    RESOURCE_LOGGER_NAME,
    CleanupIssue,
    ConnectionAcquisitionError,
    Invalidated,
    Returned,
    Unrelinquished,
)
from parallax.core.diagnostics import diagnostic_for
from parallax.core.dialect import POSTGRES
from parallax.core.execution_lifecycle import (
    AcquisitionFailed,
    AcquisitionFinished,
    AcquisitionStarted,
    AttemptBeginFailed,
    CausedFailure,
    ConnectionAcquired,
    DatabaseCallFinished,
    ExecutionEvent,
    ExecutionLifecycleHandler,
    ExecutionLifecycleHandlerError,
    FanoutLifecycleProvider,
    ReleaseFinished,
    ReleaseStarted,
    RootExecution,
    TransactionAttemptFinished,
    TransactionAttemptStarted,
)
from parallax.core.execution_lifecycle import _activity as activity_module
from parallax.core.execution_lifecycle.testing import RecordedRoot, RecordingLifecycleProvider
from parallax.core.unit_work import FixedClock
from parallax.snapshot import connect
from parallax.snapshot.handle import Database, ExecutionFailure, Transaction

_STEP: Final = 1_000
"""What one reading of the stepping clock below advances by."""


def _db(adapter: Any, provider: Any = None, model: Any = ACCOUNT) -> Database:
    return connect(adapter, model, clock=FixedClock(FIXED), lifecycle_provider=provider)


def _read(db: Database) -> None:
    db.find(mm.Account.where(mm.Account.id == 7)).result()


def _order_row(order_id: int) -> dict[str, object]:
    return {
        "id": order_id,
        "name": f"order-{order_id}",
        "sku": "A-100",
        "qty": 5,
        "price": Decimal("10.50"),
        "active": True,
        "ordered_on": dt.date(2024, 1, 5),
    }


def _active_orders() -> Any:
    return Order.where(Order.active == True)  # noqa: E712 - the query algebra's own equality


def _issue_diagnostic() -> Any:
    return diagnostic_for(RuntimeError("the pool refused the connection"))


def _handoff_failed() -> Unrelinquished:
    return Unrelinquished(
        (CleanupIssue(phase="return", code="handoff-failed", diagnostic=_issue_diagnostic()),)
    )


def _not_idle() -> Invalidated:
    return Invalidated(
        (CleanupIssue(phase="inspect", code="not-idle", diagnostic=_issue_diagnostic()),)
    )


def _unacquirable(reason: str = "preparation_failed") -> ConnectionAcquisitionError:
    return ConnectionAcquisitionError("no connection", reason=reason)  # pyright: ignore[reportArgumentType] - the caller parametrizes over reason strings the literal type spells one at a time


def _of[T: ExecutionEvent](root: RecordedRoot, kind: type[T]) -> list[T]:
    return [event for event in root.events if isinstance(event, kind)]


def _transitions(root: RecordedRoot) -> list[str]:
    return [type(event).__name__ for event in root.events]


class _SteppingClock:
    """A monotonic clock that advances by exactly :data:`_STEP` per reading.

    It makes a duration a COUNT of clock readings, which is what turns "the
    bracket is around the right call" into an exact equality instead of an
    inequality that a slow machine could satisfy by accident. Nothing but the
    lifecycle reads it, so a reading is one of the four endpoints the module
    defines.
    """

    def __init__(self) -> None:
        self.readings = 0
        self._burned = 0

    def perf_counter_ns(self) -> int:
        self.readings += 1
        return self.readings * _STEP + self._burned

    def burn(self, steps: int) -> None:
        """Advance by ``steps`` without a reading.

        Time somebody else spent: a Handler that took a while, a consumer that
        paused between pages. Nothing observes it, so it belongs to whichever
        interval was open across it and to no other — which is the claim the
        durations have to answer, and an equality answers exactly.
        """
        self._burned += steps * _STEP


def _stepping(monkeypatch: pytest.MonkeyPatch) -> _SteppingClock:
    clock = _SteppingClock()
    monkeypatch.setattr(activity_module, "time", clock)
    return clock


def _charging_cleanup(monkeypatch: pytest.MonkeyPatch, clock: _SteppingClock, steps: int) -> None:
    """Make reading a scripted context's cleanup fact cost ``steps``.

    A port may compute what its cleanup established rather than store it, so
    reading the fact is the CALLER's work happening after the resource call
    returned. Charging for it is what turns "the bracket ends at the call" into
    something a duration can be held to.
    """
    reported = ScriptedContext.cleanup_result.fget
    assert reported is not None

    def charged(context: ScriptedContext) -> Any:
        clock.burn(steps)
        return reported(context)

    monkeypatch.setattr(ScriptedContext, "cleanup_result", property(charged))


class _BurningOn:
    """A Handler that spends clock on one transition and no other."""

    def __init__(self, kind: type[ExecutionEvent], clock: _SteppingClock, steps: int) -> None:
        self._kind = kind
        self._clock = clock
        self._steps = steps
        self.seen: list[ExecutionEvent] = []

    def handle(self, event: ExecutionEvent, /) -> None:
        self.seen.append(event)
        if isinstance(event, self._kind):
            self._clock.burn(self._steps)


class _FailingOn:
    """A Handler that raises ``failure`` on the first event of one kind."""

    def __init__(self, kind: type[ExecutionEvent], failure: BaseException) -> None:
        self._kind = kind
        self._failure = failure
        self.seen: list[ExecutionEvent] = []

    def handle(self, event: ExecutionEvent, /) -> None:
        self.seen.append(event)
        if isinstance(event, self._kind):
            raise self._failure


class _Provider:
    """One fixed Handler, and whatever it was reported for."""

    def __init__(self, handler: Any) -> None:
        self._handler = handler
        self.reported: list[ExecutionLifecycleHandlerError] = []

    def open(self, execution: RootExecution, /) -> ExecutionLifecycleHandler | None:
        del execution
        return self._handler

    def report_handler_error(self, error: ExecutionLifecycleHandlerError, /) -> None:
        self.reported.append(error)


# --------------------------------------------------------------------------- #
# The shape: siblings, first and last, and containing nothing.                 #
# --------------------------------------------------------------------------- #
def test_a_failed_acquisition_carries_its_partial_cleanup_and_emits_no_release() -> None:
    # A release ends a hold, and an acquisition that granted nothing began none.
    # The cleanup the failed checkout already ran therefore rides on the
    # acquisition itself rather than on a release that would claim a hold that
    # never existed.
    partial = _not_idle()
    recorder = RecordingLifecycleProvider()
    adapter = ScriptedAdapter(acquisition_failures=[_unacquirable()], cleanup_results=[partial])

    with _db(adapter, recorder) as db, pytest.raises(ExecutionFailure):
        _read(db)

    (root,) = recorder.roots
    assert _transitions(root) == [
        "ReadStarted",
        "AcquisitionStarted",
        "AcquisitionFinished",
        "ReadFinished",
    ]
    (finished,) = _of(root, AcquisitionFinished)
    outcome = finished.outcome
    assert isinstance(outcome, AcquisitionFailed)
    assert outcome.reason == "preparation_failed"
    assert outcome.cleanup_result is partial


def test_an_acquisition_that_owned_nothing_reports_no_cleanup_at_all() -> None:
    # Absence rather than success: a checkout refused before it took anything
    # has nothing to have cleaned up, and inventing a disposition for it would
    # claim a reclamation that never ran.
    recorder = RecordingLifecycleProvider()
    adapter = ScriptedAdapter(acquisition_failures=[_unacquirable("closed")])

    with _db(adapter, recorder) as db, pytest.raises(ExecutionFailure):
        _read(db)

    (root,) = recorder.roots
    (finished,) = _of(root, AcquisitionFinished)
    outcome = finished.outcome
    assert isinstance(outcome, AcquisitionFailed)
    assert (outcome.reason, outcome.cleanup_result) == ("closed", None)


def test_an_attempt_that_could_not_acquire_finishes_begin_failed_caused_by_it() -> None:
    # The Acquisition reports its failure up under its own Activity ID, so the
    # attempt names it. The sibling case — a boundary that refused to open on a
    # connection the attempt DID acquire — finishes `direct`, which
    # `test_execution_lifecycle_transaction.py` pins.
    recorder = RecordingLifecycleProvider()
    adapter = ScriptedAdapter(acquisition_failures=[_unacquirable("timeout")])

    with _db(adapter, recorder) as db, pytest.raises(ExecutionFailure):
        db.transact(lambda _tx: None)

    (root,) = recorder.roots
    (acquisition,) = _of(root, AcquisitionStarted)
    (begin_failed,) = [event.outcome for event in _of(root, TransactionAttemptFinished)]
    assert isinstance(begin_failed, AttemptBeginFailed)
    failure = begin_failed.failure
    assert isinstance(failure, CausedFailure)
    assert failure.cause_activity_id == acquisition.activity_id


def test_a_release_reports_what_letting_go_established_without_changing_the_outcome() -> None:
    # The read published and the connection could not be handed back: two facts
    # that stand side by side, and neither rewrites the other.
    recorder = RecordingLifecycleProvider()
    unrelinquished = _handoff_failed()
    adapter = ScriptedAdapter(Read(rows=[NEW_ROW]), cleanup_results=[unrelinquished])

    with _db(adapter, recorder) as db:
        assert db.find(mm.Account.where(mm.Account.id == 7)).result() is not None

    (root,) = recorder.roots
    (release,) = _of(root, ReleaseFinished)
    assert release.cleanup_result is unrelinquished
    read_finished = root.events[-1]
    assert type(read_finished).__name__ == "ReadFinished"


def test_participating_work_acquires_nothing_of_its_own() -> None:
    # An attempt owns one connection and everything under it runs on that one:
    # a participating read is one more thing running on the transaction's
    # connection, never a second borrower of it.
    recorder = RecordingLifecycleProvider()
    adapter = ScriptedAdapter(Transact(Read(rows=[NEW_ROW]), Write()))

    def body(tx: Transaction) -> None:
        tx.find(mm.Account.where(mm.Account.id == 7)).result()
        tx.insert(mm.Account(id=8, owner="Bell", balance=Decimal("1.00")))

    with _db(adapter, recorder) as db:
        db.transact(body)

    (root,) = recorder.roots
    (attempt,) = _of(root, TransactionAttemptStarted)
    resources = _of(root, AcquisitionStarted) + _of(root, ReleaseStarted)
    # One pair, and the attempt owns both: the read, the batch, and the call
    # beneath them opened none of their own.
    assert [event.parent_activity_id for event in resources] == [attempt.activity_id] * 2
    assert adapter.acquisitions == 1


# --------------------------------------------------------------------------- #
# The clocks: what each of the three durations brackets.                       #
# --------------------------------------------------------------------------- #
def test_each_duration_brackets_its_own_resource_call_and_the_hold_spans_between(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # With a clock that advances by exactly one step per reading, a duration is
    # a COUNT of readings. The acquisition takes two adjacent readings and so
    # does the release, which is what says each brackets its own call and
    # nothing else; the hold runs from the acquisition's closing reading to the
    # release's, so it spans every reading in between — here the two the one
    # Database Call takes plus the release's own opening one.
    clock = _stepping(monkeypatch)
    recorder = RecordingLifecycleProvider()
    adapter = ScriptedAdapter(Read(rows=[NEW_ROW]))

    with _db(adapter, recorder) as db:
        _read(db)

    (root,) = recorder.roots
    (acquired,) = _of(root, AcquisitionFinished)
    (released,) = _of(root, ReleaseFinished)
    (call,) = _of(root, DatabaseCallFinished)
    assert isinstance(acquired.outcome, ConnectionAcquired)
    assert acquired.duration_ns == _STEP
    assert released.duration_ns == _STEP
    assert call.duration_ns == _STEP
    # Six readings in all: the acquisition's two, the call's two, and the
    # release's two — and the hold is the four steps from the second to the
    # sixth.
    assert clock.readings == 6
    assert released.hold_duration_ns == 4 * _STEP


def test_a_failed_acquisition_is_still_measured_around_its_own_cleanup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # The cleanup a failed entry runs happens inside the acquisition call, so it
    # is inside the acquisition's own bracket — two adjacent readings and no
    # release to measure at all.
    clock = _stepping(monkeypatch)
    recorder = RecordingLifecycleProvider()
    adapter = ScriptedAdapter(acquisition_failures=[_unacquirable()], cleanup_results=[_not_idle()])

    with _db(adapter, recorder) as db, pytest.raises(ExecutionFailure):
        _read(db)

    (root,) = recorder.roots
    (finished,) = _of(root, AcquisitionFinished)
    assert finished.duration_ns == _STEP
    assert clock.readings == 2
    assert _of(root, ReleaseFinished) == []


def test_a_handler_on_the_acquisitions_started_cannot_inflate_the_acquisition(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # The Database Call convention, applied to a resource call: the clock starts
    # only after Started has been delivered, so a Handler that spends five steps
    # there is outside the acquisition it is observing. The acquisition is
    # therefore still its own two adjacent readings and nothing else.
    clock = _stepping(monkeypatch)
    handler = _BurningOn(AcquisitionStarted, clock, 5)
    adapter = ScriptedAdapter(Read(rows=[NEW_ROW]))

    with _db(adapter, _Provider(handler)) as db:
        _read(db)

    (acquired,) = [event for event in handler.seen if isinstance(event, AcquisitionFinished)]
    assert acquired.duration_ns == _STEP


def test_the_hold_includes_the_acquisitions_own_finished_delivery(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # The one interval that deliberately CONTAINS Handler time. A hold is what
    # the operation occupied, and the connection is already the operation's
    # while the Acquisition's Finished is being delivered — so a Handler that
    # spends five steps there is inside the hold and outside every other
    # interval. The hold is otherwise the four readings between the acquisition
    # and the release, exactly as it is with no Handler at all.
    clock = _stepping(monkeypatch)
    handler = _BurningOn(AcquisitionFinished, clock, 5)
    adapter = ScriptedAdapter(Read(rows=[NEW_ROW]))

    with _db(adapter, _Provider(handler)) as db:
        _read(db)

    (acquired,) = [event for event in handler.seen if isinstance(event, AcquisitionFinished)]
    (released,) = [event for event in handler.seen if isinstance(event, ReleaseFinished)]
    assert acquired.duration_ns == _STEP
    assert released.duration_ns == _STEP
    assert released.hold_duration_ns == 9 * _STEP


def test_a_consumer_pause_between_pages_is_inside_the_streams_hold(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # A delivery holds ONE connection from its first page to its settlement, so
    # what the caller does between pages is time the connection was occupied.
    # The pause is neither an acquisition nor a release, and a hold that
    # excluded it would describe the pool's own bookkeeping rather than this
    # operation's occupancy.
    clock = _stepping(monkeypatch)
    recorder = RecordingLifecycleProvider()
    adapter = ScriptedAdapter(*paged_reads([_order_row(index) for index in (1, 2, 3)], size=2))

    with (
        _db(adapter, recorder, ORDERS_MODEL) as db,
        db.stream(_active_orders(), batch_size=2) as stream,
    ):
        for root in stream:
            del root
            clock.burn(3)

    (observed,) = recorder.roots
    (released,) = _of(observed, ReleaseFinished)
    # Three roots over two pages, so the second of the three pauses is a
    # between-pages one. The hold is every reading from the acquisition's
    # closing one — the second of the run — to the release's closing one, which
    # is the last, PLUS the nine steps the consumer spent; the release itself is
    # its own two adjacent readings, so no pause is inside it.
    assert released.duration_ns == _STEP
    assert released.hold_duration_ns == (clock.readings - 2) * _STEP + 9 * _STEP


def test_neither_duration_includes_reading_the_cleanup_fact_off_the_resource(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # What a cleanup established is read after the resource call came back, so
    # it falls outside the release's own bracket AND outside the hold that
    # bracket ends. The five steps it costs here appear in neither.
    clock = _stepping(monkeypatch)
    _charging_cleanup(monkeypatch, clock, 5)
    recorder = RecordingLifecycleProvider()
    adapter = ScriptedAdapter(Read(rows=[NEW_ROW]))

    with _db(adapter, recorder) as db:
        _read(db)

    (root,) = recorder.roots
    (released,) = _of(root, ReleaseFinished)
    assert released.duration_ns == _STEP
    assert released.hold_duration_ns == 4 * _STEP


def test_a_failed_acquisitions_duration_excludes_reading_its_cleanup_fact(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # The same endpoint on the other end: the cleanup a failed entry ran is
    # inside the acquisition call, and READING what it established is not.
    clock = _stepping(monkeypatch)
    _charging_cleanup(monkeypatch, clock, 5)
    recorder = RecordingLifecycleProvider()
    adapter = ScriptedAdapter(acquisition_failures=[_unacquirable()], cleanup_results=[_not_idle()])

    with _db(adapter, recorder) as db, pytest.raises(ExecutionFailure):
        _read(db)

    (root,) = recorder.roots
    (finished,) = _of(root, AcquisitionFinished)
    assert finished.duration_ns == _STEP


def test_an_unobserved_operation_reads_no_lifecycle_clock(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Resource handling still happens with no Provider installed; the OBSERVING
    # of it does not, and a clock read is observation. The deadline clocks the
    # runtime needs for its own budgets are its own and are not this one.
    clock = _stepping(monkeypatch)
    adapter = ScriptedAdapter(Read(rows=[NEW_ROW]), Transact(Write()))

    with _db(adapter) as db:
        _read(db)
        db.transact(lambda tx: tx.insert(mm.Account(id=8, owner="Bell", balance=Decimal("1"))))

    assert clock.readings == 0
    assert adapter.acquisitions == 2


# --------------------------------------------------------------------------- #
# Delivery: the connection outlives whatever the Handler does.                 #
# --------------------------------------------------------------------------- #
def test_a_quarantined_handler_leaves_the_rest_of_the_root_reading_no_clock(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Quarantine is permanent for the root, and after it the observation stops
    # ENTIRELY: the resource scopes take no reading for a duration nobody will
    # be told. The four readings are the acquisition's two and the call's two,
    # and the release, opened after the Handler died, takes none.
    clock = _stepping(monkeypatch)
    handler = _FailingOn(ReleaseStarted, RuntimeError("the exporter died"))
    adapter = ScriptedAdapter(Read(rows=[NEW_ROW]))

    with _db(adapter, _Provider(handler)) as db:
        _read(db)

    assert clock.readings == 4
    assert [event for event in handler.seen if isinstance(event, ReleaseFinished)] == []
    assert adapter.cleanups == [Returned()]


def test_a_fanout_whose_every_leaf_failed_stops_observing_the_root(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # A composite contains each child's failure by contract, so it returns
    # normally with nobody left to receive anything. Its answer says so, and the
    # root is quarantined on it: no Activity ID, no event and no clock reading
    # goes into a fan-out with no leaf, exactly as with a single Handler that
    # raised. The nesting is what the answer has to survive — an inner fan-out
    # answers for ITS leaves rather than for its own return.
    clock = _stepping(monkeypatch)
    inner = _Provider(_FailingOn(AcquisitionStarted, RuntimeError("the exporter died")))
    outer = _Provider(_FailingOn(AcquisitionStarted, RuntimeError("so did the other one")))
    adapter = ScriptedAdapter(Read(rows=[NEW_ROW]))
    provider = FanoutLifecycleProvider([FanoutLifecycleProvider([inner]), outer])

    with _db(adapter, provider) as db:
        _read(db)

    assert clock.readings == 0
    assert len(inner.reported) == 1
    assert len(outer.reported) == 1
    # Execution is untouched by any of it: the connection was taken, used and
    # given back while nothing was observing.
    assert (adapter.acquisitions, adapter.cleanups) == (1, [Returned()])


def test_a_fatal_exception_on_the_acquisitions_started_leaves_nothing_acquired() -> None:
    # Nothing had been taken when delivery died, so there is nothing to give
    # back — and the root is deactivated, so the acquisition that never happened
    # is reported nowhere.
    handler = _FailingOn(AcquisitionStarted, KeyboardInterrupt())
    provider = _Provider(handler)
    adapter = ScriptedAdapter(Read(rows=[NEW_ROW]))

    with _db(adapter, provider) as db, pytest.raises(KeyboardInterrupt):
        _read(db)

    assert adapter.acquisitions == 0
    assert adapter.cleanups == []
    assert provider.reported == []


def test_a_fatal_exception_on_the_acquisitions_finished_still_gives_the_connection_back() -> None:
    # The connection is real and nothing will ever be handed it, so entry
    # handling releases what it took. This is the one path where an acquisition
    # that SUCCEEDED is followed by a release nobody observes.
    handler = _FailingOn(AcquisitionFinished, KeyboardInterrupt())
    adapter = ScriptedAdapter(Read(rows=[NEW_ROW]))

    with _db(adapter, _Provider(handler)) as db, pytest.raises(KeyboardInterrupt):
        _read(db)

    assert adapter.acquisitions == 1
    assert adapter.cleanups == [Returned()]
    # Nothing modeled ran on it: the connection went straight back.
    assert adapter.calls == []


def test_a_fatal_exception_on_the_releases_started_still_relinquishes() -> None:
    # The Release scope's own opening is the only part of a release that can
    # refuse to happen, and when it does the connection still goes back.
    handler = _FailingOn(ReleaseStarted, KeyboardInterrupt())
    adapter = ScriptedAdapter(Read(rows=[NEW_ROW]))

    with _db(adapter, _Provider(handler)) as db, pytest.raises(KeyboardInterrupt):
        _read(db)

    assert adapter.acquisitions == 1
    assert adapter.cleanups == [Returned()]


def test_a_handler_quarantined_before_the_release_receives_no_cleanup_fact(
    caplog: pytest.LogCaptureFixture,
) -> None:
    # Quarantine is permanent for the root, so the release finds no Handler at
    # all rather than one that raises: a different route to the same answer, and
    # the fallback still speaks exactly once.
    handler = _FailingOn(AcquisitionStarted, RuntimeError("boom"))
    adapter = ScriptedAdapter(Read(rows=[NEW_ROW]), cleanup_results=[_handoff_failed()])

    with (
        caplog.at_level(logging.WARNING, logger=RESOURCE_LOGGER_NAME),
        _db(adapter, _Provider(handler)) as db,
    ):
        _read(db)

    assert [type(event).__name__ for event in handler.seen] == ["ReadStarted", "AcquisitionStarted"]
    assert len(_resource_records(caplog)) == 1


def test_a_fatal_exception_on_the_releases_finished_deactivates_the_root_and_propagates(
    caplog: pytest.LogCaptureFixture,
) -> None:
    # The transition carrying the cleanup fact is delivered through the same
    # containment every other one is: a control-flow or fatal exception
    # deactivates the root and propagates unchanged rather than being contained
    # as a Handler failure. The connection was already back by then, and the
    # fact nobody received reaches the fallback.
    handler = _FailingOn(ReleaseFinished, KeyboardInterrupt())
    provider = _Provider(handler)
    adapter = ScriptedAdapter(Read(rows=[NEW_ROW]), cleanup_results=[_handoff_failed()])

    with (
        caplog.at_level(logging.WARNING, logger=RESOURCE_LOGGER_NAME),
        _db(adapter, provider) as db,
        pytest.raises(KeyboardInterrupt),
    ):
        _read(db)

    assert adapter.cleanups == [_handoff_failed()]
    assert provider.reported == []
    assert len(_resource_records(caplog)) == 1


class _UnusableRuntime:
    """A runtime whose every acquisition fails with something that is not an
    acquisition error at all."""

    def __init__(self, failure: BaseException) -> None:
        self._failure = failure

    @property
    def dialect(self) -> Any:
        return POSTGRES

    @property
    def pool_metrics(self) -> None:
        return None

    def connection(self) -> Any:
        return _UnusableContext(self._failure)

    def close(self) -> None:
        return


class _UnusableContext:
    def __init__(self, failure: BaseException) -> None:
        self._failure = failure

    @property
    def cleanup_result(self) -> None:
        return None

    def __enter__(self) -> Any:
        raise self._failure

    def __exit__(self, *_exit: object) -> None:  # pragma: no cover - entry always raises
        return


class _UnusableAdapter:
    def __init__(self, failure: BaseException) -> None:
        self._failure = failure

    @property
    def dialect(self) -> Any:
        return POSTGRES

    def open(self) -> _UnusableRuntime:
        return _UnusableRuntime(self._failure)


def test_an_acquisition_that_failed_for_no_stated_reason_reports_preparation_failed() -> None:
    # An adapter states the reason on its own refusal. Anything else escaping an
    # acquisition took no connection either, and establishing execution access
    # is what did not happen — so the honest reading is `preparation_failed`
    # rather than a reason the adapter never claimed.
    recorder = RecordingLifecycleProvider()
    defect = RuntimeError("the adapter raised something else")

    with _db(_UnusableAdapter(defect), recorder) as db, pytest.raises(ExecutionFailure):
        _read(db)

    (root,) = recorder.roots
    (finished,) = _of(root, AcquisitionFinished)
    outcome = finished.outcome
    assert isinstance(outcome, AcquisitionFailed)
    assert (outcome.reason, outcome.cleanup_result) == ("preparation_failed", None)


def test_an_adapter_defect_escaping_acquisition_still_fails_the_attempts_begin() -> None:
    # An attempt that got no connection never opened a boundary, whatever the
    # reason the Acquisition derived. The route is the refusal's own: terminal,
    # no callback, no retry, and the attempt naming the Acquisition it holds —
    # not the unset-outcome fallback, which would report a rollback of a
    # transaction that never began.
    recorder = RecordingLifecycleProvider()
    defect = RuntimeError("the adapter raised something else")

    with (
        _db(_UnusableAdapter(defect), recorder) as db,
        pytest.raises(ExecutionFailure) as raised,
    ):
        db.transact(lambda _tx: None)

    assert raised.value.__cause__ is defect
    (root,) = recorder.roots
    (acquisition,) = _of(root, AcquisitionStarted)
    (begin_failed,) = [event.outcome for event in _of(root, TransactionAttemptFinished)]
    assert isinstance(begin_failed, AttemptBeginFailed)
    failure = begin_failed.failure
    assert isinstance(failure, CausedFailure)
    assert failure.cause_activity_id == acquisition.activity_id


def test_an_ordinary_handler_failure_on_the_release_changes_no_outcome() -> None:
    # Quarantine costs that Handler the rest of its root and nothing else: the
    # read still publishes and the connection still goes back.
    handler = _FailingOn(ReleaseFinished, RuntimeError("the exporter queue is full"))
    provider = _Provider(handler)
    adapter = ScriptedAdapter(Read(rows=[NEW_ROW]))

    with _db(adapter, provider) as db:
        assert db.find(mm.Account.where(mm.Account.id == 7)).result() is not None

    assert adapter.cleanups == [Returned()]
    (reported,) = provider.reported
    assert reported.diagnostic.message == "the exporter queue is full"


def test_an_operations_own_failure_survives_a_release_that_could_not_relinquish() -> None:
    # Existing primary-error precedence: what the caller catches is the failure
    # the work produced, and the cleanup fact reaches the Handler instead of
    # replacing it.
    failure = DatabaseError(category=None, native_code=None, message="the statement failed")
    unrelinquished = _handoff_failed()
    recorder = RecordingLifecycleProvider()
    adapter = ScriptedAdapter(Read(raises=failure), cleanup_results=[unrelinquished])

    with _db(adapter, recorder) as db, raises_contextualized(DatabaseError) as raised:
        _read(db)

    assert raised.value is failure
    (root,) = recorder.roots
    (release,) = _of(root, ReleaseFinished)
    assert release.cleanup_result is unrelinquished


# --------------------------------------------------------------------------- #
# The fallback: exactly one of a Handler and the restricted resource log.      #
# --------------------------------------------------------------------------- #
def _resource_records(caplog: pytest.LogCaptureFixture) -> list[logging.LogRecord]:
    return [record for record in caplog.records if record.name == RESOURCE_LOGGER_NAME]


def test_a_handler_that_received_the_cleanup_fact_silences_the_fallback_log(
    caplog: pytest.LogCaptureFixture,
) -> None:
    recorder = RecordingLifecycleProvider()
    adapter = ScriptedAdapter(Read(rows=[NEW_ROW]), cleanup_results=[_handoff_failed()])

    with (
        caplog.at_level(logging.WARNING, logger=RESOURCE_LOGGER_NAME),
        _db(adapter, recorder) as db,
    ):
        _read(db)

    (root,) = recorder.roots
    assert len(_of(root, ReleaseFinished)) == 1
    assert _resource_records(caplog) == []


def test_a_quarantined_handler_leaves_the_cleanup_fact_to_the_fallback_log(
    caplog: pytest.LogCaptureFixture,
) -> None:
    # The Handler raised ON the transition carrying the fact, so it received
    # nothing: initial acceptance is not delivery.
    handler = _FailingOn(ReleaseFinished, RuntimeError("boom"))
    adapter = ScriptedAdapter(Read(rows=[NEW_ROW]), cleanup_results=[_handoff_failed()])

    with (
        caplog.at_level(logging.WARNING, logger=RESOURCE_LOGGER_NAME),
        _db(adapter, _Provider(handler)) as db,
    ):
        _read(db)

    (record,) = _resource_records(caplog)
    assert record.levelno == logging.WARNING
    assert "return/handoff-failed" in record.getMessage()


def test_no_provider_at_all_leaves_the_cleanup_fact_to_the_fallback_log(
    caplog: pytest.LogCaptureFixture,
) -> None:
    # Failure-only reporting is the deliberate exception to the no-Provider fast
    # path: a connection nobody could give back is worth saying whether or not
    # anyone is watching.
    adapter = ScriptedAdapter(Read(rows=[NEW_ROW]), cleanup_results=[_handoff_failed()])

    with caplog.at_level(logging.WARNING, logger=RESOURCE_LOGGER_NAME), _db(adapter) as db:
        _read(db)

    assert len(_resource_records(caplog)) == 1


def test_a_clean_release_says_nothing_anywhere_but_the_event(
    caplog: pytest.LogCaptureFixture,
) -> None:
    adapter = ScriptedAdapter(Read(rows=[NEW_ROW]))

    with caplog.at_level(logging.WARNING, logger=RESOURCE_LOGGER_NAME), _db(adapter) as db:
        _read(db)

    assert _resource_records(caplog) == []


def test_a_fan_out_whose_every_child_failed_did_not_deliver_the_cleanup_fact(
    caplog: pytest.LogCaptureFixture,
) -> None:
    # The case a composite's own normal return hides. A fan-out contains each
    # child's ordinary failure by contract, so it returns after quarantining all
    # of them — and the fact reached nobody.
    children = [
        _Provider(_FailingOn(ReleaseFinished, RuntimeError("first"))),
        _Provider(_FailingOn(ReleaseFinished, RuntimeError("second"))),
    ]
    adapter = ScriptedAdapter(Read(rows=[NEW_ROW]), cleanup_results=[_handoff_failed()])

    with (
        caplog.at_level(logging.WARNING, logger=RESOURCE_LOGGER_NAME),
        _db(adapter, FanoutLifecycleProvider(children)) as db,
    ):
        _read(db)

    assert [len(child.reported) for child in children] == [1, 1]
    assert len(_resource_records(caplog)) == 1


def test_a_fan_out_one_of_whose_children_returned_did_deliver_it(
    caplog: pytest.LogCaptureFixture,
) -> None:
    # One survivor is delivery: the fact has an application-controlled export
    # path, and reporting it to the restricted log as well would report it twice.
    failing = _Provider(_FailingOn(ReleaseFinished, RuntimeError("first")))
    surviving = RecordingLifecycleProvider()
    adapter = ScriptedAdapter(Read(rows=[NEW_ROW]), cleanup_results=[_handoff_failed()])

    with (
        caplog.at_level(logging.WARNING, logger=RESOURCE_LOGGER_NAME),
        _db(adapter, FanoutLifecycleProvider([failing, surviving])) as db,
    ):
        _read(db)

    assert len(failing.reported) == 1
    assert _resource_records(caplog) == []


def test_the_fallback_log_states_the_classification_and_nothing_the_diagnostic_holds(
    caplog: pytest.LogCaptureFixture,
) -> None:
    # The rich value stays on the event for a Handler with a redaction policy;
    # this log is the floor, and it must be safe to leave on in a deployment
    # that has redacted nothing.
    adapter = ScriptedAdapter(Read(rows=[NEW_ROW]), cleanup_results=[_handoff_failed()])

    with caplog.at_level(logging.WARNING, logger=RESOURCE_LOGGER_NAME), _db(adapter) as db:
        _read(db)

    (record,) = _resource_records(caplog)
    rendered = record.getMessage()
    assert "return/handoff-failed" in rendered
    # The exception the issue carries a detached projection of reaches the log
    # nowhere, and neither does a live traceback for a formatter to render.
    assert "the pool refused the connection" not in rendered
    assert record.exc_info is None
    assert not hasattr(record, "cleanup_issues")
