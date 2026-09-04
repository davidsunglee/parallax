"""Refusing work that arrives back through the handle being observed
(m-execution-lifecycle, Docker-free).

Provider opening, event delivery, and error reporting are lifecycle contexts,
and an operation reached through the originating handle from one of them would
change the very execution it is watching. This is the one lifecycle rule that
needs ambient state, because control has left Parallax and come back through
application code — so what is graded here is the SCOPE of that state: per
handle, per thread, cleared however a context is left, and never a bar on work
an unrelated handle does.

Driven through ``connect`` and ``db.transact`` rather than against the guard, so
each case is what an application installing a badly behaved Provider would
actually see.
"""

from __future__ import annotations

import threading
from collections.abc import Callable
from typing import Any

import pytest
from _transact_support import ACCOUNT, FIXED, NEW_ROW, new_account

from _support import mirrored_models as mm
from _support.db_port import (
    Read,
    ReadCall,
    ScriptedPort,
    Transact,
    Write,
)
from parallax.core.db_port import DbPort
from parallax.core.execution_lifecycle import (
    ExecutionEvent,
    ExecutionLifecycleHandler,
    ExecutionLifecycleHandlerError,
    ExecutionLifecycleProviderError,
    ExecutionLifecycleReentryError,
    RootExecution,
)
from parallax.core.unit_work import FixedClock
from parallax.snapshot import connect
from parallax.snapshot.handle import Database, Transaction

type _Work = Callable[[], object]

UNUSED: Any = object()
"""The argument every verb below is called with where its value cannot matter.

The refusal precedes each verb's own judgement entirely, so a verb given a value
nothing could accept still answers with the refusal — and one that stopped
refusing would raise its own complaint about this object instead, which is what
makes the matrix a real assertion rather than a list of calls that all raise
something.
"""


def _db(port: DbPort, provider: Any) -> Database:
    return connect(port, ACCOUNT, clock=FixedClock(FIXED), lifecycle_provider=provider)


def _query() -> Any:
    return mm.Account.where(mm.Account.id == 7)


def _read(db: Database) -> None:
    db.find(_query()).result()


def _raising(error: BaseException) -> _Work:
    def work() -> object:
        raise error

    return work


def _once(work: _Work) -> _Work:
    """``work``, the first time it is asked for and never again.

    A Handler fires on the first event of EVERY root its Provider accepts, and
    the work these cases run opens roots of its own — legally, on another handle
    or another thread. Without this the recursion is unbounded rather than the
    single re-entrant call each case is about.
    """
    fired = False

    def run() -> object:
        nonlocal fired
        if fired:
            return None
        fired = True
        return work()

    return run


class _Handler:
    """A Handler that runs ``work`` on the first event it receives."""

    def __init__(self, work: _Work | None) -> None:
        self._work = work
        self.seen: list[ExecutionEvent] = []

    def handle(self, event: ExecutionEvent, /) -> None:
        self.seen.append(event)
        if self._work is not None and len(self.seen) == 1:
            self._work()


class _Provider:
    """A Provider that runs ``work`` from whichever of its own contexts is asked.

    One class covers all three because the question is the same in each: the
    call is legal from ordinary application code and refused from inside a
    lifecycle context, whichever context that is.
    """

    def __init__(
        self,
        *,
        opening: _Work | None = None,
        handling: _Work | None = None,
        reporting: _Work | None = None,
        handler: ExecutionLifecycleHandler | None = None,
    ) -> None:
        self._opening = opening
        self._handling = None if handling is None else _once(handling)
        self._reporting = reporting
        self._handler = handler
        self.handlers: list[_Handler] = []
        self.reported: list[ExecutionLifecycleHandlerError] = []
        self.refused_while_reporting: list[BaseException] = []

    def open(self, execution: RootExecution, /) -> ExecutionLifecycleHandler | None:
        del execution
        if self._opening is not None:
            self._opening()
        if self._handler is not None:
            return self._handler
        handler = _Handler(self._handling)
        self.handlers.append(handler)
        return handler

    def report_handler_error(self, error: ExecutionLifecycleHandlerError, /) -> None:
        self.reported.append(error)
        if self._reporting is None:
            return
        try:
            self._reporting()
        except BaseException as refusal:
            # Recorded before it is re-raised: the reporter is the one context
            # whose ordinary failure the runtime contains, so a suite that let
            # the refusal go could not tell it apart from a call that was
            # allowed through.
            self.refused_while_reporting.append(refusal)
            raise


def test_a_read_from_inside_opening_becomes_the_provider_errors_cause() -> None:
    port = ScriptedPort()
    handle: list[Database] = []
    provider = _Provider(opening=lambda: _read(handle[0]))
    db = _db(port, provider)
    handle.append(db)

    with pytest.raises(ExecutionLifecycleProviderError) as refusal:
        _read(db)
    assert isinstance(refusal.value.__cause__, ExecutionLifecycleReentryError)
    assert port.calls == [], "the refusal precedes every database call, the outer read's included"


def test_a_read_from_inside_a_handler_quarantines_it_like_any_other_failure() -> None:
    port = ScriptedPort(Read(rows=[NEW_ROW]))
    handle: list[Database] = []
    provider = _Provider(handling=lambda: _read(handle[0]))
    db = _db(port, provider)
    handle.append(db)

    # The query is untouched: re-entry escaping a Handler is an ordinary
    # delivery failure, which costs that Handler and nothing else.
    _read(db)
    (reported,) = provider.reported
    assert reported.diagnostic.qualified_type.endswith(".ExecutionLifecycleReentryError")
    assert [type(op) for op in port.calls] == [ReadCall]
    assert len(provider.handlers[0].seen) == 1


def test_a_read_from_inside_error_reporting_is_refused_and_changes_nothing() -> None:
    port = ScriptedPort(Read(rows=[NEW_ROW]))
    handle: list[Database] = []
    provider = _Provider(
        handling=_raising(RuntimeError("the exporter queue is full")),
        reporting=lambda: _read(handle[0]),
    )
    db = _db(port, provider)
    handle.append(db)

    _read(db)
    # The Handler failed ordinarily, which is what reached the reporter; the
    # reporter's own re-entry is best effort and the read still ran.
    (refusal,) = provider.refused_while_reporting
    assert isinstance(refusal, ExecutionLifecycleReentryError)
    assert [type(op) for op in port.calls] == [ReadCall]


def test_the_refusal_is_per_handle_so_an_unrelated_handle_stays_usable() -> None:
    other_port = ScriptedPort(Read(rows=[NEW_ROW]))
    other = _db(other_port, None)
    port = ScriptedPort(Read(rows=[NEW_ROW]))
    provider = _Provider(handling=lambda: _read(other))
    db = _db(port, provider)

    _read(db)
    # The handler's own read ran on the OTHER handle and was never refused, so
    # no handler failure was reported and both queries reached their ports.
    assert provider.reported == []
    assert [type(op) for op in port.calls] == [ReadCall]
    assert [type(op) for op in other_port.calls] == [ReadCall]


def test_the_refusal_is_per_thread_so_a_handler_may_hand_work_to_another() -> None:
    port = ScriptedPort(Read(rows=[NEW_ROW], times=2))
    handle: list[Database] = []
    escaped: list[BaseException] = []

    def elsewhere() -> None:
        def run() -> None:
            try:
                _read(handle[0])
            except BaseException as failure:  # pragma: no cover - recorded only when refused
                escaped.append(failure)

        worker = threading.Thread(target=run)
        worker.start()
        worker.join()

    provider = _Provider(handling=elsewhere)
    db = _db(port, provider)
    handle.append(db)

    _read(db)
    assert escaped == [], "the state belongs to the delivering thread, not to the handle"
    assert provider.reported == []


def test_the_state_is_cleared_however_a_lifecycle_context_is_left() -> None:
    port = ScriptedPort(Read(rows=[NEW_ROW]))
    provider = _Provider(handling=_raising(KeyboardInterrupt()))
    db = _db(port, provider)

    with pytest.raises(KeyboardInterrupt):
        _read(db)
    assert port.calls == [], "a fatal escape from delivery aborts its root before the port"
    # The delivery context was left by propagating rather than by returning, and
    # the handle is not left refusing everything after it.
    _read(db)
    assert [type(op) for op in port.calls] == [ReadCall]


def _database_entry_points(db: Database) -> dict[str, _Work]:
    """Every public operation a ``Database`` offers.

    The two Wire reads alone are handed a real query: the Wire view lowers its
    three accepted spellings to the canonical node before delegating, and that
    canonicalization — deterministic, reaching no state and no port — is above
    the line the refusal is drawn at.

    A stream takes the sentinel and its default page size: the refusal precedes
    the ``batch_size`` validation exactly as it precedes the query's own
    judgement, so naming a size here would only pin a second verb's argument.
    """
    return {
        "find": lambda: db.find(UNUSED),
        "stream": lambda: db.stream(UNUSED),
        "wire.find": lambda: db.wire.find(_query()),
        "wire.stream": lambda: db.wire.stream(_query()),
        "read_rows": lambda: db.read_rows(UNUSED),
        "transact": lambda: db.transact(UNUSED),
    }


def _transaction_entry_points(tx: Transaction) -> dict[str, _Work]:
    """Every public operation a ``Transaction`` offers, keyed by its spelling.

    The Wire write verbs are here under the view that publishes them, because
    the view holds the lane rather than the transaction and each of the three
    lane entries is its own refusal point.
    """
    return {
        "find": lambda: tx.find(UNUSED),
        "stream": lambda: tx.stream(UNUSED),
        "wire.find": lambda: tx.wire.find(_query()),
        "wire.stream": lambda: tx.wire.stream(_query()),
        "read_rows": lambda: tx.read_rows(UNUSED),
        "insert": lambda: tx.insert(UNUSED),
        "insert_until": lambda: tx.insert_until(UNUSED, valid_from=FIXED, until=FIXED),
        "update": lambda: tx.update(UNUSED),
        "delete": lambda: tx.delete(UNUSED),
        "terminate": lambda: tx.terminate(UNUSED),
        "update_until": lambda: tx.update_until(UNUSED, valid_from=FIXED, until=FIXED),
        "terminate_until": lambda: tx.terminate_until(UNUSED, valid_from=FIXED, until=FIXED),
        "update_where": lambda: tx.update_where(UNUSED, UNUSED),
        "delete_where": lambda: tx.delete_where(UNUSED),
        "terminate_where": lambda: tx.terminate_where(UNUSED),
        "update_until_where": lambda: tx.update_until_where(
            UNUSED, UNUSED, valid_from=FIXED, until=FIXED
        ),
        "terminate_until_where": lambda: tx.terminate_until_where(
            UNUSED, valid_from=FIXED, until=FIXED
        ),
        "wire.insert": lambda: tx.wire.insert(UNUSED, UNUSED),
        "wire.insert_until": lambda: tx.wire.insert_until(
            UNUSED, UNUSED, valid_from=FIXED, until=FIXED
        ),
        "wire.update": lambda: tx.wire.update(UNUSED, UNUSED),
        "wire.delete": lambda: tx.wire.delete(UNUSED),
        "wire.terminate": lambda: tx.wire.terminate(UNUSED),
        "wire.update_until": lambda: tx.wire.update_until(
            UNUSED, UNUSED, valid_from=FIXED, until=FIXED
        ),
        "wire.terminate_until": lambda: tx.wire.terminate_until(
            UNUSED, valid_from=FIXED, until=FIXED
        ),
        "wire.update_where": lambda: tx.wire.update_where(UNUSED, UNUSED),
        "wire.delete_where": lambda: tx.wire.delete_where(UNUSED),
        "wire.terminate_where": lambda: tx.wire.terminate_where(UNUSED),
        "wire.update_until_where": lambda: tx.wire.update_until_where(
            UNUSED, UNUSED, valid_from=FIXED, until=FIXED
        ),
        "wire.terminate_until_where": lambda: tx.wire.terminate_until_where(
            UNUSED, valid_from=FIXED, until=FIXED
        ),
    }


def _refused(entries: dict[str, _Work]) -> list[str]:
    refused: list[str] = []
    for name, work in entries.items():
        try:
            work()
        except ExecutionLifecycleReentryError:
            refused.append(name)
    return refused


def test_every_public_entry_point_of_the_handle_and_its_transaction_refuses() -> None:
    # The refusal is scoped to "the originating Handle or Transaction", which is
    # a claim about the WHOLE surface rather than about the entry points that
    # happen to be instrumented: a verb reached from a lifecycle context could
    # buffer a write, force a flush, or open a second boundary.
    port = ScriptedPort(Transact(Write()))
    handle: list[Database] = []
    opened: list[Transaction] = []
    refused: dict[str, list[str]] = {}

    class _Reentering:
        """Re-enters once the transaction the matrix needs actually exists.

        A transaction root's first events are delivered before the callback has
        run, so which event this fires on is decided by the transaction being
        available rather than by an ordinal that would have to move whenever the
        stream does.
        """

        def handle(self, event: ExecutionEvent, /) -> None:
            del event
            if not opened or refused:
                return
            refused["database"] = _refused(_database_entry_points(handle[0]))
            refused["transaction"] = _refused(_transaction_entry_points(opened[0]))

    provider = _Provider(handler=_Reentering())
    db = _db(port, provider)
    handle.append(db)

    def body(tx: Transaction) -> None:
        opened.append(tx)
        tx.insert(new_account())

    db.transact(body)

    assert refused["database"] == list(_database_entry_points(db))
    assert refused["transaction"] == list(_transaction_entry_points(opened[0]))
    assert provider.reported == [], "no verb raised anything but the refusal"
