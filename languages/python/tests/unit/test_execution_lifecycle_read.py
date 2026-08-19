"""The Read Root Execution end to end (m-execution-lifecycle, Docker-free).

A standalone read is the smallest live root there is — one Read over its own
Database Calls — so this is where the correlation envelope, the activity tree,
the Database Call payload, and the failure attribution are graded, against the
events a Provider installed through ``connect`` actually receives and never
against a projection of them.

The default path is here too, because "no Provider installed" is a behavior
rather than an absence: the same code runs, and what it must not do is allocate,
read a clock, or construct anything at all.
"""

from __future__ import annotations

import gc
from collections.abc import Sequence
from decimal import Decimal
from types import MethodType
from typing import Any, Final

import pytest
from _transact_support import ACCOUNT, FIND_SQL_UNLOCKED, FIXED, NEW_ROW, ORDERS, RecordingPort

from _support import mirrored_models as mm
from parallax.conformance import read_models
from parallax.core.db_error import DatabaseError
from parallax.core.db_port import Bind, DocumentReadOrdinals, Row
from parallax.core.execution_lifecycle import (
    CausedFailure,
    DatabaseCallFailed,
    DatabaseCallFinished,
    DatabaseCallStarted,
    DatabaseReadCompleted,
    DirectFailure,
    ExecutionEvent,
    ReadCompleted,
    ReadFailed,
    ReadFinished,
    ReadInterface,
    ReadStarted,
)
from parallax.core.execution_lifecycle import _activity as activity_module
from parallax.core.execution_lifecycle._activity import (
    ActivityTarget,
    InstalledLifecycle,
    ReadActivity,
    open_read_root,
)
from parallax.core.execution_lifecycle.testing import RecordingLifecycleProvider
from parallax.core.object_query import deserialize as deserialize_query
from parallax.core.sql_gen import CompiledRead, LoweredStatement, compile_read
from parallax.core.unit_work import FixedClock
from parallax.snapshot import connect
from parallax.snapshot.handle import Database, QueryTargetError, SnapshotMaterializationError
from parallax.snapshot.handle import _database as database_module
from parallax.snapshot.handle import _read as read_module

_ORDER_ROW: Row = {
    "id": 1,
    "name": "Ada",
    "sku": "A-100",
    "qty": 5,
    "price": Decimal("10.50"),
    "active": True,
    "ordered_on": None,
}
_ITEM_ROW: Row = {"id": 11, "order_id": 1, "sku": "x", "quantity": 1, "shipped_on": None}


class _StaticTarget:
    """An activity target whose spelling costs nothing to read."""

    @property
    def canonical(self) -> str:
        return "ledger.Account"


ACCOUNT_TARGET: Final = _StaticTarget()


def _db(port: RecordingPort, provider: Any, model: Any = ACCOUNT) -> Database:
    return connect(port, model, clock=FixedClock(FIXED), lifecycle_provider=provider)


def _transitions(events: tuple[ExecutionEvent, ...]) -> list[str]:
    return [type(event).__name__ for event in events]


def test_a_typed_find_brackets_its_one_database_call() -> None:
    recorder = RecordingLifecycleProvider()
    port = RecordingPort(rows=[NEW_ROW])
    _db(port, recorder).find(mm.Account.where(mm.Account.id == 7)).result()

    (root,) = recorder.roots
    assert root.execution.kind == "READ"
    started, call_started, call_finished, finished = root.events
    assert _transitions(root.events) == [
        "ReadStarted",
        "DatabaseCallStarted",
        "DatabaseCallFinished",
        "ReadFinished",
    ]
    # The correlation envelope: one-based and contiguous on both counters, and
    # the call is a child of the Read rather than a sibling of it.
    assert [event.sequence for event in root.events] == [1, 2, 3, 4]
    assert [event.activity_id for event in root.events] == [1, 2, 2, 1]
    assert [event.parent_activity_id for event in root.events] == [None, 1, 1, None]
    assert {event.execution_id for event in root.events} == {root.execution.id}

    assert isinstance(started, ReadStarted)
    assert (started.target, started.interface) == ("parallax.compatibility.Account", "TYPED")
    assert isinstance(call_started, DatabaseCallStarted)
    assert (call_started.target, call_started.kind) == ("parallax.compatibility.Account", "READ")
    assert isinstance(call_finished, DatabaseCallFinished)
    assert call_finished.outcome == DatabaseReadCompleted(1)
    assert isinstance(finished, ReadFinished)
    assert finished.outcome == ReadCompleted()


def test_the_call_borrows_the_exact_statement_the_port_ran() -> None:
    recorder = RecordingLifecycleProvider()
    port = RecordingPort(rows=[NEW_ROW])
    _db(port, recorder).find(mm.Account.where(mm.Account.id == 7)).result()
    (root,) = recorder.roots
    started, finished = root.events[1], root.events[3 - 1]
    assert isinstance(started, DatabaseCallStarted)
    assert isinstance(finished, DatabaseCallFinished)
    # Started and Finished repeat ONE borrowed value — neither its text nor its
    # binds are copied — and it is the canonical statement the port received.
    assert finished.statement is started.statement
    assert POSTGRES_DRIVER_SQL(started.statement.sql) == port.ops[0][1]
    assert started.statement.binds == (7,)


def POSTGRES_DRIVER_SQL(sql: str) -> str:
    return sql.replace("?", "%s")


def test_the_unlocked_standalone_statement_is_what_the_call_names() -> None:
    recorder = RecordingLifecycleProvider()
    port = RecordingPort(rows=[NEW_ROW])
    _db(port, recorder).find(mm.Account.where(mm.Account.id == 7)).result()
    (root,) = recorder.roots
    call = root.events[1]
    assert isinstance(call, DatabaseCallStarted)
    assert POSTGRES_DRIVER_SQL(call.statement.sql) == FIND_SQL_UNLOCKED


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
    port = RecordingPort(rows=[NEW_ROW])
    _db(port, _Provider(handler)).find(mm.Account.where(mm.Account.id == 7)).result()
    finished = handler.events[2]
    assert isinstance(finished, DatabaseCallFinished)
    assert finished.duration_ns < 5_000_000


def _busy_wait_ms(milliseconds: int) -> None:
    import time

    end = time.perf_counter_ns() + milliseconds * 1_000_000
    while time.perf_counter_ns() < end:
        pass


def test_a_deep_fetch_level_is_a_second_call_under_the_same_read() -> None:
    recorder = RecordingLifecycleProvider()
    port = RecordingPort(row_queue=[[_ORDER_ROW], [_ITEM_ROW]])
    _db(port, recorder, ORDERS).wire.find(
        {
            "target": "Order",
            "predicate": {"eq": {"attr": "Order.id", "value": 1}},
            "includes": [{"segments": [{"rel": "Order.items"}]}],
        }
    )

    (root,) = recorder.roots
    assert _transitions(root.events) == [
        "ReadStarted",
        "DatabaseCallStarted",
        "DatabaseCallFinished",
        "DatabaseCallStarted",
        "DatabaseCallFinished",
        "ReadFinished",
    ]
    # Every level is a child of the ONE Read the operation opened: a deep fetch
    # is one Read with many calls, never one Read per level.
    assert [event.activity_id for event in root.events] == [1, 2, 2, 3, 3, 1]
    assert [event.parent_activity_id for event in root.events] == [None, 1, 1, 1, 1, None]


def test_the_wire_and_values_lanes_name_their_own_interface() -> None:
    recorder = RecordingLifecycleProvider()
    port = RecordingPort(rows=[NEW_ROW])
    db = _db(port, recorder)
    db.wire.find({"target": "Account", "predicate": {"eq": {"attr": "Account.id", "value": 7}}})
    db.read_rows(
        deserialize_query(
            {"target": "Account", "predicate": {"eq": {"attr": "Account.id", "value": 7}}}
        )
    )
    wire_root, rows_root = recorder.roots
    for root, interface in ((wire_root, "WIRE"), (rows_root, "ROWS")):
        started = root.events[0]
        assert isinstance(started, ReadStarted)
        assert started.interface == interface


def test_a_failed_call_finishes_both_activities_and_names_its_cause() -> None:
    recorder = RecordingLifecycleProvider()
    port = RecordingPort(rows=[NEW_ROW])
    failure = DatabaseError(category="deadlock", native_code="40P01", message="deadlock detected")
    port.read_faults.append(failure)
    with pytest.raises(DatabaseError):
        _db(port, recorder).find(mm.Account.where(mm.Account.id == 7)).result()

    (root,) = recorder.roots
    assert _transitions(root.events) == [
        "ReadStarted",
        "DatabaseCallStarted",
        "DatabaseCallFinished",
        "ReadFinished",
    ]
    call_finished, read_finished = root.events[2], root.events[3]
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


def test_a_failure_after_the_call_completed_is_the_reads_own() -> None:
    # Materialization fails after every call came back, so the Read failed
    # DIRECTLY: proximity to a completed call attributes nothing.
    recorder = RecordingLifecycleProvider()
    port = RecordingPort(rows=[{"bal_id": 1, "acct_num": "A-1", "val": Decimal("5.00")}])
    with pytest.raises(SnapshotMaterializationError):
        _db(port, recorder, read_models.BALANCE_MODEL).find(
            read_models.Balance.where(read_models.Balance.id == 1)
        )

    (root,) = recorder.roots
    call_finished, read_finished = root.events[2], root.events[3]
    assert isinstance(call_finished, DatabaseCallFinished)
    assert call_finished.outcome == DatabaseReadCompleted(1)
    assert isinstance(read_finished, ReadFinished)
    outcome = read_finished.outcome
    assert isinstance(outcome, ReadFailed)
    assert isinstance(outcome.failure, DirectFailure)


def test_a_control_flow_exception_still_finishes_every_open_activity() -> None:
    # No call site writes the `BaseException` path by hand; the scope shape is
    # what keeps the transitions balanced through one.
    class _Interrupting:
        def execute(self, sql: str, binds: Any, document_reads: Any = ()) -> list[Any]:
            del sql, binds, document_reads
            raise KeyboardInterrupt

        def execute_write(self, sql: str, binds: Any) -> int:  # pragma: no cover - unused
            raise NotImplementedError

        def transaction(self, body: Any) -> Any:  # pragma: no cover - unused
            raise NotImplementedError

    recorder = RecordingLifecycleProvider()
    with pytest.raises(KeyboardInterrupt):
        _db(_Interrupting(), recorder).find(mm.Account.where(mm.Account.id == 7)).result()  # pyright: ignore[reportArgumentType] - a port that only interrupts

    (root,) = recorder.roots
    assert _transitions(root.events) == [
        "ReadStarted",
        "DatabaseCallStarted",
        "DatabaseCallFinished",
        "ReadFinished",
    ]


def test_a_read_refused_by_preflight_creates_no_root() -> None:
    # Deterministic public preflight precedes the root: an invalid target
    # creates no descriptor, calls no Provider, and reaches no port.
    recorder = RecordingLifecycleProvider()
    port = RecordingPort(rows=[NEW_ROW])
    with pytest.raises(QueryTargetError):
        _db(port, recorder).wire.find({"target": "NoSuchEntity", "predicate": {"all": {}}})
    assert recorder.roots == ()
    assert port.ops == []


def test_the_default_path_constructs_nothing_lifecycle_shaped(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # With no Provider installed the Handle branches before every
    # lifecycle-specific allocation and clock read: the seam it runs against is
    # the one shared inert activity, and nothing beside it is ever built.
    constructed: list[str] = []
    for name in ("_Publisher", "_LiveRead", "_LiveDatabaseCall"):
        original = getattr(activity_module, name)

        def counting(*args: object, _name: str = name, _original: Any = original, **kwargs: object):
            constructed.append(_name)
            return _original(*args, **kwargs)

        monkeypatch.setattr(activity_module, name, counting)

    port = RecordingPort(rows=[NEW_ROW])
    connect(port, ACCOUNT, clock=FixedClock(FIXED)).find(
        mm.Account.where(mm.Account.id == 7)
    ).result()
    assert constructed == []


def test_the_default_path_never_spells_the_target_it_is_handed() -> None:
    # The counting proof above sees lifecycle CLASSES; the payload an event
    # would have carried is a string, and a namespaced Entity's canonical
    # spelling is built rather than stored. Passing the identity and reading it
    # only where a Handler waits is what keeps the default path allocation-free
    # in a way a class count cannot observe.
    class _Probe:
        reads = 0

        @property
        def canonical(self) -> str:
            type(self).reads += 1
            return "ledger.Account"

    probe = _Probe()
    statement = LoweredStatement("select 1", ())
    with (
        open_read_root(None, target=probe, interface="TYPED") as read,
        read.database_call(statement, "READ", probe) as call,
    ):
        call.read_completed(())
    assert _Probe.reads == 0


def test_the_default_path_never_sizes_the_rows_it_is_handed() -> None:
    # The same argument one field over: a physical row count is an int, and one
    # outside the interpreter's small-integer cache is an object. Handing the
    # rows and sizing them only where a Handler waits is what keeps a large
    # unobserved result from costing an integer nobody reads.
    class _Rows:
        sizings = 0

        def __len__(self) -> int:
            type(self).sizings += 1
            return 1_000

    rows = _Rows()
    statement = LoweredStatement("select 1", ())
    with (
        open_read_root(None, target=ACCOUNT_TARGET, interface="TYPED") as read,
        read.database_call(statement, "READ", ACCOUNT_TARGET) as call,
    ):
        call.read_completed(rows)
    assert _Rows.sizings == 0


def test_the_default_path_binds_no_method_to_enter_or_leave_a_scope() -> None:
    # `with` reaches `__enter__`/`__exit__` through the descriptor protocol, so
    # an ordinary method pair would have the interpreter build a method object
    # per entry — the allocation the class counting proof above cannot see,
    # because the object it counts belongs to no lifecycle class. Static special
    # methods answer the function itself, so no scope entry binds anything.
    statement = LoweredStatement("select 1", ())
    with (
        open_read_root(None, target=ACCOUNT_TARGET, interface="TYPED") as read,
        read.database_call(statement, "READ", ACCOUNT_TARGET) as call,
    ):
        bound = [
            obj
            for obj in gc.get_objects()
            if isinstance(obj, MethodType) and (obj.__self__ is read or obj.__self__ is call)
        ]
    assert bound == []


class _Borrowing:
    """An activity that keeps what it was handed, standing in for the inert one.

    Being an activity of every kind at once is what lets one object record a
    whole read: the openers answer the shared inert activity, so a call site that
    prepared something for the lifecycle would prepare it against this.
    """

    def __init__(self) -> None:
        self.calls: list[tuple[LoweredStatement, str, ActivityTarget]] = []
        self.rows: object = None

    def __enter__(self) -> _Borrowing:
        return self

    def __exit__(self, *_exit: object) -> None:
        return None

    def database_call(
        self, statement: LoweredStatement, kind: str, target: ActivityTarget, /
    ) -> _Borrowing:
        self.calls.append((statement, kind, target))
        return self

    def read_completed(self, returned_rows: object, /) -> None:
        self.rows = returned_rows

    def write_completed(self, affected_rows: int, /) -> None: ...


class _ReturningPort(RecordingPort):
    """A port that keeps the exact list object each read returned."""

    def __init__(self, *, rows: list[Row]) -> None:
        super().__init__(rows=rows)
        self.returned: list[list[Row]] = []

    def execute(
        self,
        sql: str,
        binds: Sequence[Bind],
        document_reads: Sequence[DocumentReadOrdinals] = (),
    ) -> list[Row]:
        rows = super().execute(sql, binds, document_reads)
        self.returned.append(rows)
        return rows


def _recorded_openings(
    monkeypatch: pytest.MonkeyPatch,
) -> list[tuple[ActivityTarget, ReadInterface]]:
    """What every root opening is HANDED, in the order the composition opens them.

    An activity is what the opener answers, so no stand-in — inert, borrowing, or
    live — ever sees the root's own target and interface. Only the opening does.
    """
    recorded: list[tuple[ActivityTarget, ReadInterface]] = []

    def recording(
        installed: InstalledLifecycle | None,
        *,
        target: ActivityTarget,
        interface: ReadInterface,
    ) -> ReadActivity:
        recorded.append((target, interface))
        return open_read_root(installed, target=target, interface=interface)

    monkeypatch.setattr(database_module, "open_read_root", recording)
    return recorded


def _recorded_compilations(monkeypatch: pytest.MonkeyPatch) -> list[CompiledRead]:
    """Every compiled read the executor produces, which is where the objects a
    Database Call reports come from when the call site prepares nothing."""
    recorded: list[CompiledRead] = []

    def recording(*args: Any, **kwargs: Any) -> CompiledRead:
        compiled = compile_read(*args, **kwargs)
        recorded.append(compiled)
        return compiled

    monkeypatch.setattr(read_module, "compile_read", recording)
    return recorded


def test_a_real_call_site_hands_the_seam_only_what_the_read_already_holds(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # The probes above drive the seam directly, which is exactly what a call site
    # preparing an argument for the lifecycle would slip past: the preparation
    # would live in the caller, not in the activity. So a whole find runs here
    # with its root opening and its compilation both recorded, and every
    # lifecycle argument is graded by IDENTITY against the object the read
    # already holds — a freshly built Entity identity and a re-lowered statement
    # are EQUAL to the right ones, so anything weaker than identity would pass
    # while the call site allocated per read.
    borrowing = _Borrowing()
    monkeypatch.setattr(activity_module, "INERT", borrowing)
    openings = _recorded_openings(monkeypatch)
    compilations = _recorded_compilations(monkeypatch)

    port = _ReturningPort(rows=[NEW_ROW])
    connect(port, ACCOUNT, clock=FixedClock(FIXED)).find(
        mm.Account.where(mm.Account.id == 7)
    ).result()

    (compiled,) = compilations
    (root_target, interface), *further_openings = openings
    (statement, kind, call_target), *further_calls = borrowing.calls
    assert further_openings == []
    assert further_calls == []
    assert (interface, kind) == ("TYPED", "READ")
    assert root_target is compiled.target
    assert call_target is compiled.target
    assert statement is compiled.statement
    assert borrowing.rows is port.returned[0]
    # The borrowed statement is the one the port ran, not merely the one the
    # compilation produced: the two together leave a re-lowered spelling nowhere.
    assert POSTGRES_DRIVER_SQL(statement.sql) == port.ops[0][1]
