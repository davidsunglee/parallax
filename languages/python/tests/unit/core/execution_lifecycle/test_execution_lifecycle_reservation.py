"""A key reservation in the lifecycle tree, over a scripted port.

A reservation is a ``reservation`` Read of the attempt whose insert needed the
key: it owns its own acquisition, its one row-returning Database Call, and its
release, beside the attempt's own lease. A failure is attributed within that
Read — to the acquisition or the call that failed, or to the Read itself where
the answer was refused once the connection was back — and the attempt it belongs
to keeps going. A key still held locally emits nothing.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Callable, Sequence
from typing import Any

import pytest

from parallax.conformance._lifecycle_recording import RecordedRoot, RecordingLifecycleProvider
from parallax.conformance.scripted_clock import FixedClock
from parallax.core import ConnectionAcquisitionError, UsageError
from parallax.core.execution_lifecycle import (
    AcquisitionFailed,
    AcquisitionFinished,
    AcquisitionStarted,
    AttemptCommitted,
    CausedFailure,
    ConnectionAcquired,
    DatabaseCallFailed,
    DatabaseCallFinished,
    DatabaseCallStarted,
    DatabaseReadCompleted,
    DirectFailure,
    ExecutionEvent,
    ReadCompleted,
    ReadFailed,
    ReadFinished,
    ReadStarted,
    TransactionAttemptFinished,
)
from parallax.core.internal.db_error import DatabaseError
from parallax.snapshot import TxnContext, connect
from tests._support import mirrored_models as mm
from tests._support.bindings import TEST_BINDING
from tests._support.db_port import Read, ScriptedAdapter, Transact, Write

_FIXED = dt.datetime(2024, 1, 1, tzinfo=dt.UTC)
_ROW: dict[str, object] = {
    "first_key": 100,
    "increment": 30,
    "minimum": 1,
    "maximum": 2**63 - 1,
    "cycles": False,
    "data_type": "bigint",
}


def _recorded(port: ScriptedAdapter, body: Callable[[TxnContext], object]) -> RecordedRoot:
    recorder = RecordingLifecycleProvider()
    with connect(
        port,
        mm.PK_KEY_SEQUENCE_MODEL,
        clock=FixedClock(_FIXED),
        binding=TEST_BINDING,
        lifecycle_provider=recorder,
    ) as root:
        root.using_database_login().transact(body)
    (recorded,) = recorder.roots
    return recorded


def _tree(events: Sequence[ExecutionEvent]) -> list[tuple[str, int, int | None]]:
    return [(type(event).__name__, event.activity_id, event.parent_activity_id) for event in events]


def _reservation(events: Sequence[ExecutionEvent], read: int) -> list[ExecutionEvent]:
    """The reservation Read ``read``'s own events and its children's, in order."""
    return [
        event for event in events if event.activity_id == read or event.parent_activity_id == read
    ]


def _read_ids(events: Sequence[ExecutionEvent]) -> list[int]:
    return [
        event.activity_id
        for event in events
        if isinstance(event, ReadStarted) and event.purpose == "reservation"
    ]


def test_a_reservation_is_a_read_owning_its_acquisition_call_and_release() -> None:
    port = ScriptedAdapter(Transact(Read(rows=[_ROW]), Write()))

    root = _recorded(port, lambda tx: [tx.insert(mm.KeySequencePass(holder=h)) for h in "abc"])

    events = root.events
    (read,) = _read_ids(events)
    started = next(event for event in events if isinstance(event, ReadStarted))
    assert (started.target, started.parent_activity_id) == ("parallax.compatibility.Pass", 2)
    # The attempt's own lease is activity 3; the reservation's is its Read's.
    assert _tree(_reservation(events, read)) == [
        ("ReadStarted", read, 2),
        ("AcquisitionStarted", read + 1, read),
        ("AcquisitionFinished", read + 1, read),
        ("DatabaseCallStarted", read + 2, read),
        ("DatabaseCallFinished", read + 2, read),
        ("ReleaseStarted", read + 3, read),
        ("ReleaseFinished", read + 3, read),
        ("ReadFinished", read, 2),
    ]
    acquisition, acquired, call, finished_call, *_, finished = _reservation(events, read)[1:]
    assert isinstance(acquisition, AcquisitionStarted)
    assert acquisition.route_policy is None
    assert isinstance(acquired, AcquisitionFinished)
    assert isinstance(acquired.outcome, ConnectionAcquired)
    assert acquired.outcome.route == "writer"
    assert isinstance(call, DatabaseCallStarted)
    assert (call.kind, call.statement.binds) == ("read", ("px.pass_ids",))
    assert isinstance(finished_call, DatabaseCallFinished)
    assert finished_call.outcome == DatabaseReadCompleted(1)
    assert isinstance(finished, ReadFinished)
    assert finished.outcome == ReadCompleted()
    # Three keys from one block: the second and third inserts emit nothing.
    assert sum(isinstance(event, ReadStarted) for event in events) == 1


def _failed_statement() -> tuple[ScriptedAdapter, type[BaseException]]:
    failure = DatabaseError(category=None, native_code="57014", message="canceled")
    return ScriptedAdapter(Transact(Read(raises=failure), Write())), DatabaseError


def _failed_acquisition() -> tuple[ScriptedAdapter, type[BaseException]]:
    refusal = ConnectionAcquisitionError("budget spent", reason="timeout")
    return (
        ScriptedAdapter(Transact(Write()), acquisition_failures=[None, refusal]),
        ConnectionAcquisitionError,
    )


def _refused_answer() -> tuple[ScriptedAdapter, type[BaseException]]:
    return ScriptedAdapter(Transact(Read(rows=[_ROW | {"cycles": True}]), Write())), UsageError


@pytest.mark.parametrize(
    ("scripted", "expected", "cause"),
    [
        (
            _failed_statement,
            [
                "ReadStarted",
                "AcquisitionStarted",
                "AcquisitionFinished",
                "DatabaseCallStarted",
                "DatabaseCallFinished",
                "ReleaseStarted",
                "ReleaseFinished",
                "ReadFinished",
            ],
            4,
        ),
        (
            _failed_acquisition,
            ["ReadStarted", "AcquisitionStarted", "AcquisitionFinished", "ReadFinished"],
            2,
        ),
        (
            _refused_answer,
            [
                "ReadStarted",
                "AcquisitionStarted",
                "AcquisitionFinished",
                "DatabaseCallStarted",
                "DatabaseCallFinished",
                "ReleaseStarted",
                "ReleaseFinished",
                "ReadFinished",
            ],
            None,
        ),
    ],
    ids=["statement", "acquisition", "refused-answer"],
)
def test_a_failed_reservation_is_attributed_within_its_read_and_the_attempt_commits(
    scripted: Callable[[], tuple[ScriptedAdapter, type[BaseException]]],
    expected: list[str],
    cause: int | None,
) -> None:
    port, raised = scripted()

    def body(tx: TxnContext) -> None:
        with pytest.raises(raised):
            tx.insert(mm.KeySequencePass(holder="lost"))
        tx.insert(mm.KeySequencePass(id=7, holder="given"))

    events = _recorded(port, body).events
    (read,) = _read_ids(events)
    reservation = _reservation(events, read)
    assert [type(event).__name__ for event in reservation] == expected
    finished = reservation[-1]
    assert isinstance(finished, ReadFinished)
    assert isinstance(finished.outcome, ReadFailed)
    failure: Any = finished.outcome.failure
    if cause is None:
        # Refused once its connection was back: the Read's own failure.
        assert isinstance(failure, DirectFailure)
    else:
        child = reservation[cause]
        assert isinstance(child, (AcquisitionFinished, DatabaseCallFinished))
        assert isinstance(child.outcome, (AcquisitionFailed, DatabaseCallFailed))
        assert failure == CausedFailure(failure.diagnostic, child.activity_id)
    attempt = next(event for event in events if isinstance(event, TransactionAttemptFinished))
    assert isinstance(attempt.outcome, AttemptCommitted)
