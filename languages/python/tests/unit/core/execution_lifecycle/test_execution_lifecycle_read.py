"""The Read Root Execution end to end (m-execution-lifecycle, Docker-free).

A standalone read is the smallest live root there is — one Read over its own
Database Calls — so this is where the activity tree, the Database Call payload,
and the failure attribution are graded, against the events a Provider installed
through ``connect`` actually receives and never against a projection of them.

The default path is here too, because "no Provider installed" is a behavior
rather than an absence: the same code runs, and what it must not do is allocate,
read a clock, or construct anything at all.
"""

from __future__ import annotations

import sys
from collections.abc import Iterator, Sequence
from decimal import Decimal
from types import MethodType
from typing import Any, Final

import pytest

from parallax.conformance._lifecycle_recording import RecordingLifecycleProvider
from parallax.conformance.scripted_clock import FixedClock
from parallax.core.execution_lifecycle import (
    CausedFailure,
    DatabaseCallFailed,
    DatabaseCallFinished,
    DatabaseCallStarted,
    DatabaseReadCompleted,
    DirectFailure,
    ExecutionEvent,
    ReadFailed,
    ReadFinished,
    ReadStarted,
)
from parallax.core.execution_lifecycle._activity import open_read_root
from parallax.core.internal.base import UsageError
from parallax.core.internal.db_error import DatabaseError
from parallax.core.internal.db_port import (
    Bind,
    DatabaseAdapter,
    DocumentReadOrdinals,
    MappingRow,
    Row,
)
from parallax.core.internal.dialect import POSTGRES
from parallax.core.internal.sql_gen import LoweredStatement
from parallax.snapshot import ScopedDatabase, connect
from tests._support import mirrored_models as mm
from tests._support.bindings import TEST_BINDING
from tests._support.db_port import (
    ConnectsAsItself,
    Read,
    ReadCall,
    ScriptedAdapter,
)
from tests._support.errors import raises_code
from tests._support.root_ownership import own_root
from tests.unit._transact_support import ACCOUNT, FIXED, NEW_ROW, ORDERS
from tests.unit.memory_instruments import (
    in_a_child_interpreter,
    serve_one_measurement,
    tracked_objects,
)

_ORDER_ROW: MappingRow = {
    "id": 1,
    "name": "Ada",
    "sku": "A-100",
    "qty": 5,
    "price": Decimal("10.50"),
    "active": True,
    "ordered_on": None,
}
_ITEM_ROW: MappingRow = {"id": 11, "order_id": 1, "sku": "x", "quantity": 1, "shipped_on": None}
_TAG_ROW: MappingRow = {"id": 21, "order_id": 1, "label": "urgent", "priority": 2}


class _StaticTarget:
    """An activity target whose spelling costs nothing to read."""

    @property
    def canonical(self) -> str:
        return "ledger.Account"


ACCOUNT_TARGET: Final = _StaticTarget()


def _db(adapter: DatabaseAdapter, provider: Any, model: Any = ACCOUNT) -> ScopedDatabase:
    return own_root(
        connect(
            adapter,
            model,
            clock=FixedClock(FIXED),
            lifecycle_provider=provider,
            binding=TEST_BINDING,
        )
    ).using_database_login()


def _transitions(events: tuple[ExecutionEvent, ...]) -> list[str]:
    return [type(event).__name__ for event in events]


def test_a_call_reports_the_statement_the_port_ran() -> None:
    recorder = RecordingLifecycleProvider()
    port = ScriptedAdapter(Read(rows=[NEW_ROW]))
    _db(port, recorder).find(mm.Account.where(mm.Account.id == 7)).result()
    (root,) = recorder.roots
    read, started, finished = root.events[0], root.events[3], root.events[4]
    assert isinstance(read, ReadStarted)
    assert read.purpose == "typed"
    assert isinstance(started, DatabaseCallStarted)
    assert isinstance(finished, DatabaseCallFinished)
    # Started and Finished report one statement, the canonical one the port
    # received.
    assert finished.statement == started.statement
    (executed,) = (call for call in port.calls if isinstance(call, ReadCall))
    assert started.statement.sql == executed.sql
    assert started.statement.binds == (7,)


def test_a_duration_excludes_the_handler_time_around_it() -> None:
    # The clock starts only after Started has been delivered, so a Handler that
    # sleeps cannot inflate the call it observes.
    class _SlowHandler:
        def __init__(self) -> None:
            self.events: list[ExecutionEvent] = []

        def handle(self, event: ExecutionEvent, /) -> None:
            self.events.append(event)
            _busy_wait_ms(5)

    class _Provider:
        def __init__(self, handler: _SlowHandler) -> None:
            self.handler = handler

        def open(self, execution: Any, /) -> _SlowHandler:
            del execution
            return self.handler

        def report_handler_error(self, error: Any, /) -> None:
            raise AssertionError("no handler failed")

    handler = _SlowHandler()
    port = ScriptedAdapter(Read(rows=[NEW_ROW]))
    _db(port, _Provider(handler)).find(mm.Account.where(mm.Account.id == 7)).result()
    finished = handler.events[4]
    assert isinstance(finished, DatabaseCallFinished)
    assert finished.duration_ns < 5_000_000


def _busy_wait_ms(milliseconds: int) -> None:
    import time

    end = time.perf_counter_ns() + milliseconds * 1_000_000
    while time.perf_counter_ns() < end:
        pass


def test_a_deep_fetch_level_is_a_second_call_under_the_same_read() -> None:
    recorder = RecordingLifecycleProvider()
    port = ScriptedAdapter(Read(rows=[_ORDER_ROW]), Read(rows=[_ITEM_ROW]))
    _db(port, recorder, ORDERS).wire.find(
        {
            "target": "Order",
            "predicate": {"eq": {"path": "Order.id", "value": 1}},
            "includes": [{"segments": [{"rel": "Order.items"}]}],
        }
    )

    (root,) = recorder.roots
    assert _transitions(root.events) == [
        "ReadStarted",
        "AcquisitionStarted",
        "AcquisitionFinished",
        "DatabaseCallStarted",
        "DatabaseCallFinished",
        "DatabaseCallStarted",
        "DatabaseCallFinished",
        "ReleaseStarted",
        "ReleaseFinished",
        "ReadFinished",
    ]
    # Every level is a child of the ONE Read the operation opened: a deep fetch
    # is one Read with many calls, never one Read per level — and both levels
    # run on the ONE connection the read acquired before either of them and
    # released after both, which is what "a read holds its connection through
    # publication" looks like read off the stream.
    assert [event.activity_id for event in root.events] == [1, 2, 2, 3, 3, 4, 4, 5, 5, 1]
    assert [event.parent_activity_id for event in root.events] == [None] + [1] * 8 + [None]


def test_pipelined_sibling_levels_keep_one_ordered_call_per_statement() -> None:
    recorder = RecordingLifecycleProvider()
    port = ScriptedAdapter(Read(rows=[_ORDER_ROW]), Read(rows=[_ITEM_ROW]), Read(rows=[_TAG_ROW]))
    _db(port, recorder, ORDERS).wire.find(
        {
            "target": "Order",
            "predicate": {"eq": {"path": "Order.id", "value": 1}},
            "includes": [
                {"segments": [{"rel": "Order.items"}]},
                {"segments": [{"rel": "Order.tags"}]},
            ],
        }
    )

    (root,) = recorder.roots
    assert _transitions(root.events) == [
        "ReadStarted",
        "AcquisitionStarted",
        "AcquisitionFinished",
        "DatabaseCallStarted",
        "DatabaseCallFinished",
        "DatabaseCallStarted",
        "DatabaseCallStarted",
        "DatabaseCallFinished",
        "DatabaseCallFinished",
        "ReleaseStarted",
        "ReleaseFinished",
        "ReadFinished",
    ]
    call_events = [
        event
        for event in root.events
        if isinstance(event, DatabaseCallStarted | DatabaseCallFinished)
    ]
    assert [event.activity_id for event in call_events] == [3, 3, 4, 5, 5, 4]
    assert [event.outcome for event in call_events if isinstance(event, DatabaseCallFinished)] == [
        DatabaseReadCompleted(1)
    ] * 3
    assert [call for call in port.calls if isinstance(call, ReadCall)] == port.calls
    assert len(port.calls) == 3


def test_a_failed_sibling_pipeline_balances_every_open_call() -> None:
    recorder = RecordingLifecycleProvider()
    failure = DatabaseError(category="deadlock", native_code="40P01", message="deadlock detected")
    port = ScriptedAdapter(Read(rows=[_ORDER_ROW]), Read(rows=[_ITEM_ROW]), Read(raises=failure))

    with pytest.raises(DatabaseError):
        _db(port, recorder, ORDERS).wire.find(
            {
                "target": "Order",
                "predicate": {"eq": {"path": "Order.id", "value": 1}},
                "includes": [
                    {"segments": [{"rel": "Order.items"}]},
                    {"segments": [{"rel": "Order.tags"}]},
                ],
            }
        )

    (root,) = recorder.roots
    assert _transitions(root.events) == [
        "ReadStarted",
        "AcquisitionStarted",
        "AcquisitionFinished",
        "DatabaseCallStarted",
        "DatabaseCallFinished",
        "DatabaseCallStarted",
        "DatabaseCallStarted",
        "DatabaseCallFinished",
        "DatabaseCallFinished",
        "ReleaseStarted",
        "ReleaseFinished",
        "ReadFinished",
    ]
    pipeline_finishes = [
        event for event in root.events[5:9] if isinstance(event, DatabaseCallFinished)
    ]
    assert [event.activity_id for event in pipeline_finishes] == [5, 4]
    assert all(isinstance(event.outcome, DatabaseCallFailed) for event in pipeline_finishes)
    read_finished = root.events[-1]
    assert isinstance(read_finished, ReadFinished)
    assert isinstance(read_finished.outcome, ReadFailed)
    caused = read_finished.outcome.failure
    assert isinstance(caused, CausedFailure)
    assert caused.cause_activity_id == 5


def test_a_failed_call_finishes_both_activities_and_names_its_cause() -> None:
    recorder = RecordingLifecycleProvider()
    failure = DatabaseError(category="deadlock", native_code="40P01", message="deadlock detected")
    port = ScriptedAdapter(Read(raises=failure))
    with pytest.raises(DatabaseError):
        _db(port, recorder).find(mm.Account.where(mm.Account.id == 7)).result()

    (root,) = recorder.roots
    assert _transitions(root.events) == [
        "ReadStarted",
        "AcquisitionStarted",
        "AcquisitionFinished",
        "DatabaseCallStarted",
        "DatabaseCallFinished",
        "ReleaseStarted",
        "ReleaseFinished",
        "ReadFinished",
    ]
    call_finished, read_finished = root.events[4], root.events[7]
    assert isinstance(call_finished, DatabaseCallFinished)
    outcome = call_finished.outcome
    assert isinstance(outcome, DatabaseCallFailed)
    assert (outcome.diagnostic.category, outcome.diagnostic.native_code) == ("deadlock", "40P01")

    assert isinstance(read_finished, ReadFinished)
    read_outcome = read_finished.outcome
    assert isinstance(read_outcome, ReadFailed)
    # The Read names the call it failed because of, and reuses that call's own
    # diagnostic object rather than rendering the same exception twice.
    caused = read_outcome.failure
    assert isinstance(caused, CausedFailure)
    assert caused.cause_activity_id == call_finished.activity_id
    assert caused.diagnostic is outcome.diagnostic.failure


class _UnwalkableRows(list[Row]):
    """An answer a call can count and nothing can walk."""

    def __iter__(self) -> Iterator[Row]:
        raise ValueError("these rows cannot be walked")


class _UnwalkablePort(ScriptedAdapter):
    def execute(
        self,
        sql: str,
        binds: Sequence[Bind],
        document_reads: Sequence[DocumentReadOrdinals] = (),
        *,
        read_only: bool = False,
    ) -> list[Row]:
        return _UnwalkableRows(super().execute(sql, binds, document_reads, read_only=read_only))


def test_a_failure_past_a_completed_call_is_the_reads_own() -> None:
    # The call came back and counted its rows, and what failed came after it, so
    # the Read failed DIRECTLY: proximity to a completed call attributes nothing.
    recorder = RecordingLifecycleProvider()
    port = _UnwalkablePort(Read(rows=[NEW_ROW]))
    with pytest.raises(ValueError, match="cannot be walked"):
        _db(port, recorder).find(mm.Account.where(mm.Account.id == 7)).result()

    (root,) = recorder.roots
    call_finished, read_finished = root.events[4], root.events[7]
    assert isinstance(call_finished, DatabaseCallFinished)
    assert call_finished.outcome == DatabaseReadCompleted(1)
    assert isinstance(read_finished, ReadFinished)
    outcome = read_finished.outcome
    assert isinstance(outcome, ReadFailed)
    assert isinstance(outcome.failure, DirectFailure)


def test_a_control_flow_exception_still_finishes_every_open_activity() -> None:
    # No call site writes the `BaseException` path by hand; the scope shape is
    # what keeps the transitions balanced through one.
    class _Interrupting(ConnectsAsItself):
        dialect = POSTGRES

        def execute(
            self, sql: str, binds: Any, document_reads: Any = (), *, read_only: bool = False
        ) -> list[Any]:
            del sql, binds, document_reads
            raise KeyboardInterrupt

        def execute_write(self, sql: str, binds: Any) -> int:  # pragma: no cover - unused
            raise NotImplementedError

        def transaction(self, body: Any) -> Any:  # pragma: no cover - unused
            raise NotImplementedError

    recorder = RecordingLifecycleProvider()
    with pytest.raises(KeyboardInterrupt):
        _db(_Interrupting(), recorder).find(mm.Account.where(mm.Account.id == 7)).result()

    (root,) = recorder.roots
    # The release is in the list for the same reason the call's Finished is: a
    # scope emits its end however its body leaves, so the connection an
    # interrupt escaped through is still given back and still observed.
    assert _transitions(root.events) == [
        "ReadStarted",
        "AcquisitionStarted",
        "AcquisitionFinished",
        "DatabaseCallStarted",
        "DatabaseCallFinished",
        "ReleaseStarted",
        "ReleaseFinished",
        "ReadFinished",
    ]


def test_a_read_refused_by_preflight_creates_no_root() -> None:
    # Deterministic public preflight precedes the root: an invalid target
    # creates no descriptor, calls no Provider, and reaches no port.
    recorder = RecordingLifecycleProvider()
    port = ScriptedAdapter()
    with raises_code(UsageError, "query-target-not-in-model"):
        _db(port, recorder).wire.find({"target": "NoSuchEntity", "predicate": {"true": {}}})
    assert recorder.roots == ()
    assert port.calls == []


def test_a_typed_read_refused_by_preflight_creates_no_root() -> None:
    # The same claim at the Typed door, asserted rather than inferred from the
    # shared gate: `Person` is a perfectly declared Entity of another model, so
    # the connected model is what makes the query unanswerable — and it is
    # answered before a root exists and before the port is reached.
    recorder = RecordingLifecycleProvider()
    port = ScriptedAdapter()
    with raises_code(UsageError, "query-target-not-in-model"):
        _db(port, recorder).find(mm.Person.where(mm.Person.id == 1))
    assert recorder.roots == ()
    assert port.calls == []


@in_a_child_interpreter
def test_the_default_path_binds_no_method_to_enter_or_leave_a_scope() -> None:
    # `with` reaches `__enter__`/`__exit__` through the descriptor protocol, so
    # an ordinary method pair would have the interpreter build a method object
    # per entry. Static special methods answer the function itself, so no scope
    # entry binds anything.
    statement = LoweredStatement("select 1", ())
    with (
        open_read_root(None, target=ACCOUNT_TARGET, purpose="typed", edition="edition") as read,
        read.database_call(statement, "read", ACCOUNT_TARGET) as call,
    ):
        bound = [
            obj
            for obj in tracked_objects()
            if isinstance(obj, MethodType) and (obj.__self__ is read or obj.__self__ is call)
        ]
    assert bound == []


if __name__ == "__main__":
    serve_one_measurement(sys.argv[1])
