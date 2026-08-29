"""The Snapshot Stream Root Execution end to end (m-execution-lifecycle, Docker-free).

The seventh activity kind, observed where it is produced rather than where it is
consumed: every event here comes out of `_activity.py` through a Provider
installed at ``connect``, driven by the shipped ``db.stream`` and ``tx.stream``
against a canned `m-db-port`. The two consumers — the logger and the conformance
normalizer — have rendered these transitions since before anything emitted one,
so what was missing was never the vocabulary.

Four claims bound the suite. A stream's TREE is one activity per page and none
per root, which is what keeps observing a million-root delivery the same cost per
page as observing a hundred-root one. Its ENDING is the one thing only the stream
knows: exhaustion is announced where it is discovered, a caller who stopped early
is the default, and Parallax's own failure is neither. Its ATTRIBUTION follows the
page boundary — a page that failed is the batch's failure and the stream's cause,
while a root that failed to publish reaches a batch that already completed and is
the stream's own. And its CORRELATION says where a stream sits: a standalone one
is a root, a participating one is a child of the attempt, and the dependency batch
a page flushes out is that page's ordered sibling rather than its parent.
"""

from __future__ import annotations

import datetime as dt
from decimal import Decimal
from typing import Any, Final

import pytest
from _transact_support import ACCOUNT, account_db

from _support import mirrored_models as mm
from _support.db_port import (
    BeginCall,
    CommitCall,
    Read,
    ReadCall,
    ScriptedPort,
    Transact,
    Write,
)
from parallax.conformance.story_models import ORDERS_MODEL, Order
from parallax.core.db_error import DatabaseError
from parallax.core.db_port import DbPort, Row
from parallax.core.execution_lifecycle import (
    CausedFailure,
    DirectFailure,
    ExecutionEvent,
    ExecutionLifecycleHandler,
    ExecutionLifecycleHandlerError,
    RootExecution,
    SnapshotStreamFinished,
    SnapshotStreamStarted,
    StreamBatchCompleted,
    StreamBatchFailed,
    StreamBatchFinished,
    StreamBatchStarted,
    StreamClosedEarly,
    StreamExhausted,
    StreamFailed,
    WriteBatchFinished,
    WriteBatchStarted,
)
from parallax.core.execution_lifecycle.testing import RecordedRoot, RecordingLifecycleProvider
from parallax.core.unit_work import FixedClock
from parallax.snapshot import InvalidDataError, connect
from parallax.snapshot.handle import Database, QueryTargetError, Transaction

_FIXED: Final = dt.datetime(2024, 6, 1, tzinfo=dt.UTC)


def _order_row(order_id: int) -> Row:
    return {
        "id": order_id,
        "name": f"order-{order_id}",
        "sku": "A-100",
        "qty": 5,
        "price": Decimal("10.50"),
        "active": True,
        "ordered_on": dt.date(2024, 1, 5),
    }


def _keyless_order_row() -> Row:
    return {**_order_row(0), "id": None}


def _account_row(account_id: int) -> Row:
    return {
        "id": account_id,
        "owner": f"owner-{account_id}",
        "balance": Decimal("100.00"),
        "version": 1,
    }


class _Declining:
    """A Provider that refuses every root, which is the other observed path."""

    def __init__(self) -> None:
        self.opened: list[RootExecution] = []

    def open(self, execution: RootExecution, /) -> ExecutionLifecycleHandler | None:
        self.opened.append(execution)
        return None

    def report_handler_error(self, error: ExecutionLifecycleHandlerError, /) -> None:
        raise AssertionError(error)  # pragma: no cover - a declined root has no handler to fail


class _FailingHandler:
    """A Handler that fails ordinarily at the ``fail_at``-th event it receives."""

    def __init__(self, *, fail_at: int) -> None:
        self._fail_at = fail_at
        self.seen: list[ExecutionEvent] = []

    def handle(self, event: ExecutionEvent, /) -> None:
        self.seen.append(event)
        if len(self.seen) == self._fail_at:
            raise RuntimeError("the exporter's queue is full")


class _QuarantiningProvider:
    """One handler for every root, and the out-of-band reports it earns."""

    def __init__(self, handler: _FailingHandler) -> None:
        self._handler = handler
        self.reported: list[ExecutionLifecycleHandlerError] = []

    def open(self, execution: RootExecution, /) -> ExecutionLifecycleHandler:
        del execution
        return self._handler

    def report_handler_error(self, error: ExecutionLifecycleHandlerError, /) -> None:
        self.reported.append(error)


def _connected(port: DbPort, model: Any, provider: Any) -> Database:
    return connect(port, model, clock=FixedClock(_FIXED), lifecycle_provider=provider)


def _orders(port: DbPort, recorder: RecordingLifecycleProvider) -> Database:
    return _connected(port, ORDERS_MODEL, recorder)


def _accounts(port: DbPort, recorder: RecordingLifecycleProvider) -> Database:
    return _connected(port, ACCOUNT, recorder)


def _active_orders() -> Any:
    return Order.where(Order.active == True)  # noqa: E712 - the query algebra's own equality


def _transitions(root: RecordedRoot) -> list[str]:
    return [type(event).__name__ for event in root.events]


def _envelope(root: RecordedRoot) -> list[tuple[int, int, int | None]]:
    return [(event.sequence, event.activity_id, event.parent_activity_id) for event in root.events]


def _of[T: ExecutionEvent](root: RecordedRoot, kind: type[T]) -> list[T]:
    return [event for event in root.events if isinstance(event, kind)]


# --------------------------------------------------------------------------- #
# The tree: one activity per page, and none per root.                          #
# --------------------------------------------------------------------------- #
def test_a_standalone_stream_is_its_own_root_and_opens_one_batch_per_page() -> None:
    recorder = RecordingLifecycleProvider()
    port = ScriptedPort(Read(rows=[_order_row(1), _order_row(2)]), Read(rows=[_order_row(3)]))
    with _orders(port, recorder).stream(_active_orders(), batch_size=2) as stream:
        assert [root.id for root in stream] == [1, 2, 3]

    (root,) = recorder.roots
    assert root.execution.kind == "SNAPSHOT_STREAM"
    assert _transitions(root) == [
        "SnapshotStreamStarted",
        "StreamBatchStarted",
        "DatabaseCallStarted",
        "DatabaseCallFinished",
        "StreamBatchFinished",
        "StreamBatchStarted",
        "DatabaseCallStarted",
        "DatabaseCallFinished",
        "StreamBatchFinished",
        "SnapshotStreamFinished",
    ]
    # The stream is the root activity — its parent is null and no other event's
    # is — each page is its child, and each page's call is the page's own. A
    # Database Call under a Snapshot Stream directly would mean the batch was not
    # the page-read activity, which is exactly what the batch exists to be.
    assert _envelope(root) == [
        (1, 1, None),
        (2, 2, 1),
        (3, 3, 2),
        (4, 3, 2),
        (5, 2, 1),
        (6, 4, 1),
        (7, 5, 4),
        (8, 5, 4),
        (9, 4, 1),
        (10, 1, None),
    ]
    (started,) = _of(root, SnapshotStreamStarted)
    assert (started.target, started.interface, started.batch_size) == (
        "parallax.compatibility.Order",
        "TYPED",
        2,
    )
    (finished,) = _of(root, SnapshotStreamFinished)
    assert finished.outcome == StreamExhausted()


def test_a_wire_stream_reports_its_own_interface() -> None:
    recorder = RecordingLifecycleProvider()
    port = ScriptedPort(Read(rows=[_order_row(1)]))
    with _orders(port, recorder).wire.stream(_active_orders(), batch_size=2) as stream:
        assert len(list(stream)) == 1

    (root,) = recorder.roots
    (started,) = _of(root, SnapshotStreamStarted)
    assert started.interface == "WIRE"


def test_the_empty_terminal_page_is_a_batch_of_its_own_and_the_stream_still_exhausts() -> None:
    # A full final page proves nothing, so exhaustion costs one more root
    # statement — and that statement is a PAGE, so it is a Stream Batch like any
    # other and completes like any other. The batch whose page returned nothing
    # is what "including an empty terminal page" names.
    recorder = RecordingLifecycleProvider()
    port = ScriptedPort(Read(rows=[_order_row(1), _order_row(2)]), Read(rows=[]))
    with _orders(port, recorder).stream(_active_orders(), batch_size=2) as stream:
        assert [root.id for root in stream] == [1, 2]

    (root,) = recorder.roots
    assert [type(event).__name__ for event in root.events].count("StreamBatchStarted") == 2
    assert [outcome.outcome for outcome in _of(root, StreamBatchFinished)] == [
        StreamBatchCompleted(),
        StreamBatchCompleted(),
    ]
    (finished,) = _of(root, SnapshotStreamFinished)
    assert finished.outcome == StreamExhausted()


def test_a_stream_nobody_enters_opens_no_root() -> None:
    # Construction emits nothing, so a stream built and dropped calls no Provider
    # at all — the same rule that keeps a refused read from opening one.
    recorder = RecordingLifecycleProvider()
    _orders(ScriptedPort(), recorder).stream(_active_orders())
    assert recorder.roots == ()


def test_a_stream_refused_at_the_gate_opens_no_root() -> None:
    # Deterministic public preflight precedes Root Execution creation, and for a
    # stream that gate is at context ENTRY rather than at the call. A target the
    # model does not carry is therefore refused with no root and no Provider
    # call, exactly as it is for a find.
    recorder = RecordingLifecycleProvider()
    stream = _accounts(ScriptedPort(), recorder).stream(_active_orders())
    with pytest.raises(QueryTargetError), stream:
        pass  # pragma: no cover - entering is what raises
    assert recorder.roots == ()


def test_the_event_count_grows_with_pages_and_not_with_roots() -> None:
    # The reason per-root publication is deliberately NOT an activity: two
    # deliveries at one page size cost two events per page plus two for the
    # stream, whatever each page delivered. Twelve roots in three pages weigh
    # exactly what three roots in three pages weigh.
    def delivered(count: int, *, size: int) -> int:
        recorder = RecordingLifecycleProvider()
        rows = [_order_row(identifier) for identifier in range(1, count + 1)]
        pages = [rows[at : at + size] for at in range(0, count, size)]
        port = ScriptedPort(*(Read(rows=page) for page in pages), Read())
        with _orders(port, recorder).stream(_active_orders(), batch_size=size) as stream:
            assert len(list(stream)) == count
        (root,) = recorder.roots
        return len(root.events)

    assert delivered(3, size=1) == delivered(12, size=4) == 2 + 4 * 4


# --------------------------------------------------------------------------- #
# The ending: exhausted, closed early, or failed — and only the stream knows.  #
# --------------------------------------------------------------------------- #
def test_breaking_out_of_the_loop_finishes_closed_early() -> None:
    recorder = RecordingLifecycleProvider()
    port = ScriptedPort(Read(rows=[_order_row(1), _order_row(2)]))
    with _orders(port, recorder).stream(_active_orders(), batch_size=2) as stream:
        for root in stream:
            if root.id == 1:
                break

    (root,) = recorder.roots
    # One page was read and no second one was asked for, which is the whole
    # observable difference between stopping early and running out.
    assert _transitions(root).count("StreamBatchStarted") == 1
    (finished,) = _of(root, SnapshotStreamFinished)
    assert finished.outcome == StreamClosedEarly()


def test_a_caller_exception_inside_the_scope_is_closed_early_and_still_propagates() -> None:
    # Closed Early describes only that the stream ended early. It does not
    # rewrite the caller's control flow — the exception that ended the iteration
    # leaves the scope as itself — and it is not Failed, which is reserved for
    # Parallax's own work.
    recorder = RecordingLifecycleProvider()
    port = ScriptedPort(Read(rows=[_order_row(1), _order_row(2)]))
    stop = RuntimeError("the caller's own")
    with (
        pytest.raises(RuntimeError) as raised,
        _orders(port, recorder).stream(_active_orders(), batch_size=2) as stream,
    ):
        for _ in stream:
            raise stop
    assert raised.value is stop

    (root,) = recorder.roots
    (finished,) = _of(root, SnapshotStreamFinished)
    assert finished.outcome == StreamClosedEarly()


def test_exhaustion_finishes_the_stream_where_it_was_discovered() -> None:
    # Read INSIDE the still-open scope, which is the only place the claim is
    # observable: a stream that banked its outcome until the scope closed would
    # be indistinguishable from this one everywhere else, and here it would
    # report nothing at all yet.
    recorder = RecordingLifecycleProvider()
    port = ScriptedPort(Read(rows=[_order_row(1)]))
    with _orders(port, recorder).stream(_active_orders(), batch_size=2) as stream:
        assert len(list(stream)) == 1
        (root,) = recorder.roots
        (finished,) = _of(root, SnapshotStreamFinished)
        assert finished.outcome == StreamExhausted()
        assert finished is root.events[-1]


def test_once_exhausted_a_later_caller_error_cannot_rewrite_the_outcome() -> None:
    # Exhaustion having already finished the stream is what leaves the caller's
    # own failure with nothing to end: it propagates as itself and the delivery
    # stays reported as it happened, with no second Finished for the same
    # activity.
    recorder = RecordingLifecycleProvider()
    port = ScriptedPort(Read(rows=[_order_row(1)]))
    with (
        pytest.raises(RuntimeError),
        _orders(port, recorder).stream(_active_orders(), batch_size=2) as stream,
    ):
        assert len(list(stream)) == 1
        raise RuntimeError("after the delivery ran out")

    (root,) = recorder.roots
    (finished,) = _of(root, SnapshotStreamFinished)
    assert finished.outcome == StreamExhausted()
    assert finished is root.events[-1]


# --------------------------------------------------------------------------- #
# Attribution: the page boundary decides who owns a failure.                   #
# --------------------------------------------------------------------------- #
def test_a_page_read_failure_fails_its_batch_first_and_causes_the_stream_failure() -> None:
    recorder = RecordingLifecycleProvider()
    failure = DatabaseError(category="deadlock", native_code="40P01", message="deadlock detected")
    port = ScriptedPort(Read(rows=[_order_row(1), _order_row(2)]), Read(raises=failure))
    with (
        pytest.raises(DatabaseError),
        _orders(port, recorder).stream(_active_orders(), batch_size=2) as stream,
    ):
        assert [root.id for root in stream] == [1, 2]

    (root,) = recorder.roots
    batches = _of(root, StreamBatchFinished)
    (stream_finished,) = _of(root, SnapshotStreamFinished)
    completed, failed = batches
    assert completed.outcome == StreamBatchCompleted()
    assert isinstance(failed.outcome, StreamBatchFailed)
    # The batch finishes BEFORE the stream does, and the stream names it — one
    # link at a time, and never the Database Call two levels down.
    assert failed.sequence < stream_finished.sequence
    assert isinstance(stream_finished.outcome, StreamFailed)
    caused = stream_finished.outcome.failure
    assert isinstance(caused, CausedFailure)
    assert caused.cause_activity_id == failed.activity_id
    assert caused.diagnostic is failed.outcome.failure.diagnostic


def test_a_per_root_publication_failure_leaves_its_batch_completed_and_fails_the_stream() -> None:
    # Publication runs one root at a time OUTSIDE every batch, so a root whose
    # stored state contradicted the model reaches a batch that has already
    # finished Completed. The stream therefore fails DIRECTLY: proximity to the
    # page that produced the row attributes nothing.
    recorder = RecordingLifecycleProvider()
    port = ScriptedPort(Read(rows=[_order_row(1), _keyless_order_row()]))
    with (
        pytest.raises(InvalidDataError),
        _orders(port, recorder).stream(_active_orders(), batch_size=2) as stream,
    ):
        assert [root.id for root in stream] == [1]

    (root,) = recorder.roots
    (batch,) = _of(root, StreamBatchFinished)
    assert batch.outcome == StreamBatchCompleted()
    (stream_finished,) = _of(root, SnapshotStreamFinished)
    assert isinstance(stream_finished.outcome, StreamFailed)
    assert isinstance(stream_finished.outcome.failure, DirectFailure)


def test_a_failure_the_caller_caught_still_finishes_the_stream_failed() -> None:
    # Failed is what Parallax's own work did, not what left the caller's block:
    # a caller that catches the failure and leaves the scope normally has not
    # turned a failed delivery into a caller who stopped early.
    recorder = RecordingLifecycleProvider()
    port = ScriptedPort(Read(rows=[_order_row(1), _keyless_order_row()]))
    with _orders(port, recorder).stream(_active_orders(), batch_size=2) as stream:  # noqa: SIM117 - the refusal is caught INSIDE the scope, which is the claim
        with pytest.raises(InvalidDataError):
            list(stream)

    (root,) = recorder.roots
    (stream_finished,) = _of(root, SnapshotStreamFinished)
    assert isinstance(stream_finished.outcome, StreamFailed)


# --------------------------------------------------------------------------- #
# Correlation: where a stream sits, and what a page's flush sits beside.       #
# --------------------------------------------------------------------------- #
def test_a_transactional_stream_is_a_child_of_the_attempt() -> None:
    recorder = RecordingLifecycleProvider()
    port = ScriptedPort(
        Transact(Read(rows=[_account_row(1), _account_row(2)]), Read(rows=[_account_row(3)]))
    )

    def fn(tx: Transaction) -> list[int]:
        with tx.stream(mm.Account.where(mm.Account.id >= 1), batch_size=2) as stream:
            return [account.id for account in stream]

    assert _accounts(port, recorder).transact(fn) == [1, 2, 3]

    (root,) = recorder.roots
    assert root.execution.kind == "TRANSACTION_INVOCATION"
    assert _transitions(root) == [
        "TransactionInvocationStarted",
        "TransactionAttemptStarted",
        "SnapshotStreamStarted",
        "StreamBatchStarted",
        "DatabaseCallStarted",
        "DatabaseCallFinished",
        "StreamBatchFinished",
        "StreamBatchStarted",
        "DatabaseCallStarted",
        "DatabaseCallFinished",
        "StreamBatchFinished",
        "SnapshotStreamFinished",
        "TransactionAttemptFinished",
        "TransactionInvocationFinished",
    ]
    (started,) = _of(root, SnapshotStreamStarted)
    attempt = root.events[1]
    assert started.parent_activity_id == attempt.activity_id
    # Five correlation levels, which is the longest chain the algebra admits:
    # invocation, attempt, stream, page, call.
    page = _of(root, StreamBatchStarted)[0]
    assert page.parent_activity_id == started.activity_id
    assert root.events[4].parent_activity_id == page.activity_id


def test_a_pages_dependency_write_batch_is_that_pages_ordered_sibling() -> None:
    # The flush precedes the batch rather than running inside it, so the two are
    # siblings under the attempt in that order — the same relation a dependency
    # batch and the Read it enables already have. A page whose batch opened first
    # would report the flush as work the page did.
    recorder = RecordingLifecycleProvider()
    port = ScriptedPort(
        Transact(Read(rows=[_account_row(1)]), Write(), Read(rows=[_account_row(2)]), Read(rows=[]))
    )

    def fn(tx: Transaction) -> None:
        with tx.stream(mm.Account.where(mm.Account.id >= 1), batch_size=1) as stream:
            for account in stream:
                if account.id == 1:
                    tx.update(account.edit(balance=Decimal("125.00")))

    _accounts(port, recorder).transact(fn)

    (root,) = recorder.roots
    # Compared as the whole ORDER rather than as a relation between two events:
    # the batch that would open too early is a batch, and any pairwise reading
    # can be satisfied by a LATER page instead of the one the flush preceded.
    assert _transitions(root) == [
        "TransactionInvocationStarted",
        "TransactionAttemptStarted",
        "SnapshotStreamStarted",
        "StreamBatchStarted",
        "DatabaseCallStarted",
        "DatabaseCallFinished",
        "StreamBatchFinished",
        "WriteBatchStarted",
        "DatabaseCallStarted",
        "DatabaseCallFinished",
        "WriteBatchFinished",
        "StreamBatchStarted",
        "DatabaseCallStarted",
        "DatabaseCallFinished",
        "StreamBatchFinished",
        "StreamBatchStarted",
        "DatabaseCallStarted",
        "DatabaseCallFinished",
        "StreamBatchFinished",
        "SnapshotStreamFinished",
        "TransactionAttemptFinished",
        "TransactionInvocationFinished",
    ]
    (stream_started,) = _of(root, SnapshotStreamStarted)
    (write_started,) = _of(root, WriteBatchStarted)
    # Siblings: the flush's batch names the ATTEMPT the stream itself names, so
    # it is beside the page rather than under it.
    assert write_started.parent_activity_id == stream_started.parent_activity_id
    (write_finished,) = _of(root, WriteBatchFinished)
    forced = _of(root, StreamBatchStarted)[1]
    assert write_finished.sequence < forced.sequence


def test_a_participating_stream_that_the_callback_left_early_is_closed_early() -> None:
    # A transaction that commits says nothing about how the delivery inside it
    # ended: the stream's own outcome is the stream's, and the attempt's is the
    # attempt's.
    recorder = RecordingLifecycleProvider()
    port = ScriptedPort(Transact(Read(rows=[_account_row(1), _account_row(2)])))

    def fn(tx: Transaction) -> int:
        with tx.stream(mm.Account.where(mm.Account.id >= 1), batch_size=2) as stream:
            for account in stream:
                return account.id
        return 0  # pragma: no cover - the first root always arrives

    assert _accounts(port, recorder).transact(fn) == 1

    (root,) = recorder.roots
    (finished,) = _of(root, SnapshotStreamFinished)
    assert finished.outcome == StreamClosedEarly()


def test_a_declined_stream_root_costs_its_opening_and_delivers_unchanged() -> None:
    # The second costed path: a Provider that refuses the root is asked once and
    # told nothing, and the delivery below it runs exactly as an unobserved one
    # does — every page, every root.
    provider = _Declining()
    port = ScriptedPort(Read(rows=[_order_row(1), _order_row(2)]), Read(rows=[_order_row(3)]))
    with _connected(port, ORDERS_MODEL, provider).stream(_active_orders(), batch_size=2) as stream:
        assert [root.id for root in stream] == [1, 2, 3]
    assert [execution.kind for execution in provider.opened] == ["SNAPSHOT_STREAM"]
    assert [type(op) for op in port.calls] == [ReadCall, ReadCall]


def test_a_handler_quarantined_mid_delivery_stops_its_events_and_not_the_delivery() -> None:
    # An ordinary Handler failure quarantines that Handler for the rest of its
    # root and changes no execution semantics: the pages after it open, read,
    # and publish, and the stream's own ending reaches nobody. The events stop
    # at the one that failed rather than resuming later.
    handler = _FailingHandler(fail_at=2)
    provider = _QuarantiningProvider(handler)
    port = ScriptedPort(Read(rows=[_order_row(1), _order_row(2)]), Read(rows=[_order_row(3)]))
    with _connected(port, ORDERS_MODEL, provider).stream(_active_orders(), batch_size=2) as stream:
        assert [root.id for root in stream] == [1, 2, 3]

    assert [type(event).__name__ for event in handler.seen] == [
        "SnapshotStreamStarted",
        "StreamBatchStarted",
    ]
    assert [type(op) for op in port.calls] == [ReadCall, ReadCall]
    (reported,) = provider.reported
    assert reported.diagnostic.message == "the exporter's queue is full"


def test_a_participating_stream_under_a_quarantined_root_opens_no_scope_of_its_own() -> None:
    # The stream a Transaction Attempt opens asks whether delivery is still live
    # before it opens at all, which the standalone root never has to: an
    # invocation whose Handler was already quarantined has nothing left to tell,
    # so the stream does the rest of its lifecycle work not at all.
    handler = _FailingHandler(fail_at=1)
    provider = _QuarantiningProvider(handler)
    port = ScriptedPort(Transact(Read(rows=[_account_row(1)]), Read(rows=[])))

    def fn(tx: Transaction) -> list[int]:
        with tx.stream(mm.Account.where(mm.Account.id >= 1), batch_size=1) as stream:
            return [account.id for account in stream]

    assert _connected(port, ACCOUNT, provider).transact(fn) == [1]
    assert [type(event).__name__ for event in handler.seen] == ["TransactionInvocationStarted"]
    assert [type(op) for op in port.calls] == [BeginCall, ReadCall, ReadCall, CommitCall]


def test_an_unobserved_stream_delivers_its_roots_and_publishes_nothing() -> None:
    # The default path runs the same code an observed one runs, and the whole of
    # what it must not do is observable here as nothing at all being opened.
    port = ScriptedPort(Read(rows=[_account_row(1)]), Read(rows=[]))
    with account_db(port).stream(mm.Account.where(mm.Account.id >= 1), batch_size=1) as stream:
        assert [account.id for account in stream] == [1]
