"""What a connected handle owns, and how long each operation holds a connection.

The resource contract has two halves and they are proven apart. The Postgres
runtime's half — what a checkout, a cleanup, and a shutdown ESTABLISH — is
``test_postgres_pool.py``'s. This file is the other half: which operation
acquires, when it lets go, and what a handle owns for its own lifetime, all of
it driver-free over the scripted adapter.

The pins that matter most are about letting go early. An exhausted stream must
stop occupying capacity at the moment it is over rather than when its caller
happens to leave the ``with`` block; an attempt must release before it finishes,
so a retry acquires afresh rather than replaying over what its predecessor left;
and an operation that could not acquire at all must fail with the reason
acquisition gave rather than with anything about the cleanup that followed.
"""

from __future__ import annotations

import datetime as dt
import logging
from decimal import Decimal
from typing import Any

import pytest

from parallax.conformance.story_models import ORDERS_MODEL, Account, Order
from parallax.core.db_error import DatabaseError
from parallax.core.db_port import (
    RESOURCE_LOGGER_NAME,
    CleanupIssue,
    ConnectionAcquisitionError,
    Invalidated,
    Returned,
    Unrelinquished,
    report_resource_issues,
)
from parallax.core.diagnostics import diagnostic_for
from parallax.core.unit_work import FixedClock
from parallax.snapshot import connect
from parallax.snapshot.handle import Database, ExecutionFailure, Transaction
from tests._support.db_port import (
    ConnectsAsItself,
    Read,
    RefusingAdapter,
    ScriptedAdapter,
    Transact,
    Write,
)
from tests.unit._transact_support import ACCOUNT, FIXED, deadlock

_ACCOUNT_ROW = {"id": 1, "owner": "Newton", "balance": Decimal("10.00"), "version": 1}


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


def _orders_query() -> Any:
    return Order.where(Order.active == True)  # noqa: E712 - the query algebra's own equality


def _db(adapter: Any, model: Any = ACCOUNT) -> Database:
    return connect(adapter, model, clock=FixedClock(FIXED))


def _account_query() -> Any:
    return Account.where(Account.id == 1)


# --------------------------------------------------------------------------- #
# Composition and ownership.                                                   #
# --------------------------------------------------------------------------- #


def test_connecting_opens_the_runtime_the_handle_then_owns() -> None:
    adapter = ScriptedAdapter()
    db = _db(adapter)
    assert adapter.closes == 0
    db.close()
    assert adapter.closes == 1


def test_explicit_close_and_leaving_the_scope_are_the_same_thing() -> None:
    adapter = ScriptedAdapter()
    with _db(adapter):
        pass
    assert adapter.closes == 1


def test_close_is_idempotent() -> None:
    adapter = ScriptedAdapter()
    db = _db(adapter)
    db.close()
    db.close()
    # The runtime is asked twice and answers once; a handle a caller closes
    # while unwinding must not object to being closed again.
    assert adapter.closes == 2


def test_two_handles_from_one_configuration_own_two_independent_runtimes() -> None:
    adapter = ScriptedAdapter(Read(rows=[_ACCOUNT_ROW]))
    first = _db(adapter)
    second = _db(adapter)

    first.close()

    # Closing one leaves the other working, which is what makes reusing a
    # configuration safe rather than a way to share a resource by accident.
    assert second.find(_account_query()).result().owner == "Newton"
    second.close()


def test_a_model_that_could_never_be_served_costs_no_resource() -> None:
    adapter = RefusingAdapter()
    with pytest.raises(Exception, match="snapshot-class-backed-model-required"):
        connect(adapter, "not a model")  # pyright: ignore[reportArgumentType] - the runtime refusal of an untyped caller is what this proves


# --------------------------------------------------------------------------- #
# One connection per operation.                                                #
# --------------------------------------------------------------------------- #


def test_an_eager_read_holds_one_connection_through_its_whole_execution() -> None:
    # Every root and relationship statement, the conversion, and the
    # publication it is materialized into: a graph half-built from rows is not a
    # result anything may return.
    adapter = ScriptedAdapter(Read(rows=[_ACCOUNT_ROW]))
    with _db(adapter) as db:
        db.find(_account_query()).result()

    assert (adapter.acquisitions, adapter.cleanups) == (1, [Returned()])


def test_two_eager_reads_acquire_twice() -> None:
    adapter = ScriptedAdapter(Read(rows=[_ACCOUNT_ROW]), Read(rows=[_ACCOUNT_ROW]))
    with _db(adapter) as db:
        db.find(_account_query()).result()
        db.find(_account_query()).result()
    assert adapter.acquisitions == 2


def test_an_eager_read_that_fails_still_releases_and_keeps_its_own_failure() -> None:
    failure = DatabaseError(category=None, native_code=None, message="the statement failed")
    adapter = ScriptedAdapter(Read(raises=failure))
    with _db(adapter) as db, pytest.raises(ExecutionFailure) as raised:
        db.find(_account_query()).result()

    assert raised.value.__cause__ is failure
    assert adapter.cleanups == [Returned()]


def test_a_transaction_attempt_holds_one_connection_and_a_retry_acquires_afresh() -> None:
    # Nothing of a failed attempt's resource is carried into its successor; the
    # pool may well hand back the same physical connection, which is its
    # business rather than the retry loop's.
    adapter = ScriptedAdapter(
        Transact(Read(rows=[_ACCOUNT_ROW]), commit=deadlock()),
        Transact(Read(rows=[_ACCOUNT_ROW])),
    )
    with _db(adapter) as db:
        db.transact(lambda tx: tx.find(_account_query()).result())

    assert adapter.acquisitions == 2
    assert adapter.cleanups == [Returned(), Returned()]


def test_participating_work_inherits_the_attempts_connection_and_returns_nothing() -> None:
    adapter = ScriptedAdapter(Transact(Read(rows=[_ACCOUNT_ROW]), Read(rows=[_ACCOUNT_ROW])))
    with _db(adapter) as db:

        def body(tx: Transaction) -> None:
            tx.find(_account_query()).result()
            tx.find(_account_query()).result()

        db.transact(body)

    assert adapter.acquisitions == 1


def test_a_stream_acquires_at_its_first_page_and_not_at_scope_entry() -> None:
    adapter = ScriptedAdapter(Read(rows=[_order_row(1)]), Read(rows=[]))
    with _db(adapter, ORDERS_MODEL) as db:
        delivery = db.stream(_orders_query(), batch_size=2)
        assert adapter.acquisitions == 0
        with delivery as roots:
            assert adapter.acquisitions == 0
            assert list(roots)
            assert adapter.acquisitions == 1


def test_an_exhausted_stream_releases_where_it_ends_rather_than_at_its_scope_exit() -> None:
    # A delivery that is over must not keep capacity until the caller happens to
    # leave its `with` block.
    adapter = ScriptedAdapter(Read(rows=[_order_row(1)]), Read(rows=[]))
    with _db(adapter, ORDERS_MODEL) as db:
        with db.stream(_orders_query(), batch_size=2) as roots:
            assert list(roots)
            assert adapter.cleanups == [Returned()]
        assert adapter.cleanups == [Returned()]


def test_a_stream_a_caller_abandoned_releases_at_its_scope_exit() -> None:
    # A caller who simply stopped reading reaches no terminal state, so the
    # scope exit is where its connection goes back.
    adapter = ScriptedAdapter(Read(rows=[_order_row(1), _order_row(2)]))
    with _db(adapter, ORDERS_MODEL) as db:
        with db.stream(_orders_query(), batch_size=2) as roots:
            next(iter(roots))
            assert adapter.cleanups == []
        assert adapter.cleanups == [Returned()]


def test_a_stream_closed_before_its_first_page_releases_nothing() -> None:
    adapter = ScriptedAdapter()
    with _db(adapter, ORDERS_MODEL) as db, db.stream(_orders_query(), batch_size=2):
        pass
    assert (adapter.acquisitions, adapter.cleanups) == (0, [])


def test_a_failed_stream_releases_where_it_failed() -> None:
    failure = DatabaseError(category=None, native_code=None, message="the page failed")
    adapter = ScriptedAdapter(Read(raises=failure))
    with _db(adapter, ORDERS_MODEL) as db, pytest.raises(ExecutionFailure):  # noqa: SIM117 - one combined `with` would nest the raises inside the handle's own scope
        with db.stream(_orders_query(), batch_size=2) as roots:
            list(roots)
    assert adapter.cleanups == [Returned()]


# --------------------------------------------------------------------------- #
# Acquisition failure.                                                         #
# --------------------------------------------------------------------------- #


def _unacquirable(reason: str = "closed") -> ConnectionAcquisitionError:
    return ConnectionAcquisitionError("no connection", reason=reason)  # pyright: ignore[reportArgumentType] - the caller parametrizes over reason strings the literal type spells one at a time


def test_an_attempt_that_cannot_acquire_is_terminal_and_runs_no_callback() -> None:
    # No boundary opened and no callback ran, so this is the same terminal
    # outcome a refused BEGIN reaches: nothing to undo and nothing to replay.
    refusal = _unacquirable()
    adapter = ScriptedAdapter(acquisition_failures=[refusal])
    ran: list[str] = []

    with _db(adapter) as db, pytest.raises(ExecutionFailure) as raised:
        db.transact(lambda _tx: ran.append("body"))

    # Named under the edition the attempt adopted — the failure is the
    # operation's, and acquisition is where that operation stopped.
    assert raised.value.__cause__ is refusal
    assert ran == []
    assert adapter.acquisitions == 0


def test_an_attempt_that_cannot_acquire_is_not_retried_however_retriable_it_looks() -> None:
    adapter = ScriptedAdapter(acquisition_failures=[_unacquirable("timeout")])
    with _db(adapter) as db, pytest.raises(ExecutionFailure):
        db.transact(lambda _tx: None, retries=5)
    assert adapter.acquisitions == 0


def test_an_eager_read_that_cannot_acquire_fails_with_the_reason_acquisition_gave() -> None:
    # It never uses transaction begin-failure machinery: the read fails its own
    # activity with the acquisition error, under its adopted edition.
    refusal = _unacquirable("queue_rejected")
    adapter = ScriptedAdapter(acquisition_failures=[refusal])

    with _db(adapter) as db, pytest.raises(ExecutionFailure) as raised:
        db.find(_account_query())

    assert raised.value.__cause__ is refusal


def test_a_stream_that_cannot_acquire_its_first_page_fails_the_delivery() -> None:
    refusal = _unacquirable("timeout")
    adapter = ScriptedAdapter(acquisition_failures=[refusal])

    with _db(adapter, ORDERS_MODEL) as db, pytest.raises(ExecutionFailure) as raised:  # noqa: SIM117 - one combined `with` would nest the raises inside the handle's own scope
        with db.stream(_orders_query(), batch_size=2) as roots:
            list(roots)

    assert raised.value.__cause__ is refusal


def test_a_failed_entry_consumes_the_partial_cleanup_it_left_behind() -> None:
    # Python never calls `__exit__` for an `__enter__` that raised, so the
    # context cleans up itself and the facts are read back rather than left on a
    # value nobody looks at again.
    partial = Invalidated((CleanupIssue(phase="inspect", code="not-idle", diagnostic=_issue()),))
    adapter = ScriptedAdapter(
        acquisition_failures=[_unacquirable("preparation_failed")], cleanup_results=[partial]
    )

    with _db(adapter) as db, pytest.raises(ExecutionFailure):
        db.find(_account_query())

    assert adapter.cleanups == [partial]


def _issue() -> Any:
    return diagnostic_for(RuntimeError("its state was INTRANS"))


# --------------------------------------------------------------------------- #
# Ordinary cleanup problems preserve what the operation established.           #
# --------------------------------------------------------------------------- #


def test_a_successful_read_survives_a_cleanup_problem() -> None:
    unrelinquished = Unrelinquished(
        (CleanupIssue(phase="return", code="handoff-failed", diagnostic=_issue()),)
    )
    adapter = ScriptedAdapter(Read(rows=[_ACCOUNT_ROW]), cleanup_results=[unrelinquished])

    with _db(adapter) as db:
        assert db.find(_account_query()).result().owner == "Newton"


def test_a_committed_transaction_survives_a_cleanup_problem() -> None:
    unrelinquished = Unrelinquished(
        (CleanupIssue(phase="dispose", code="close-failed", diagnostic=_issue()),)
    )
    adapter = ScriptedAdapter(Transact(Write()), cleanup_results=[unrelinquished])

    with _db(adapter) as db:

        def body(tx: Transaction) -> str:
            tx.insert(Account(id=2, owner="Linus", balance=Decimal("1.00")))
            return "committed"

        assert db.transact(body) == "committed"


def test_an_operations_own_failure_is_not_replaced_by_a_cleanup_problem() -> None:
    failure = DatabaseError(category=None, native_code=None, message="the statement failed")
    unrelinquished = Unrelinquished(
        (CleanupIssue(phase="return", code="handoff-failed", diagnostic=_issue()),)
    )
    adapter = ScriptedAdapter(Read(raises=failure), cleanup_results=[unrelinquished])

    with _db(adapter) as db, pytest.raises(ExecutionFailure) as raised:
        db.find(_account_query()).result()

    assert raised.value.__cause__ is failure


# --------------------------------------------------------------------------- #
# The restricted resource logger.                                              #
# --------------------------------------------------------------------------- #


def test_a_cleanup_problem_reports_its_phase_code_and_fixed_text_and_nothing_else(
    caplog: pytest.LogCaptureFixture,
) -> None:
    # This log is the floor, not a second export path: it must be safe to leave
    # on in a deployment that has redacted nothing, so the rich diagnostic, the
    # native message, and any structured extra stay out of it.
    native = RuntimeError("FATAL: password authentication failed for user 'admin'")
    issue = CleanupIssue(phase="return", code="handoff-failed", diagnostic=diagnostic_for(native))

    with caplog.at_level(logging.WARNING, logger=RESOURCE_LOGGER_NAME):
        report_resource_issues("operation", Unrelinquished((issue,)))

    (record,) = caplog.records
    assert record.name == RESOURCE_LOGGER_NAME
    assert "return/handoff-failed" in record.getMessage()
    assert "password" not in record.getMessage()
    assert record.exc_info is None


def test_nothing_is_reported_for_an_absent_result_or_one_without_issues(
    caplog: pytest.LogCaptureFixture,
) -> None:
    # Failure-only reporting: a working path is not instrumented here.
    with caplog.at_level(logging.WARNING, logger=RESOURCE_LOGGER_NAME):
        report_resource_issues("operation", None)
        report_resource_issues("shutdown", Returned())
    assert caplog.records == []


def test_reporting_never_raises_whatever_logging_does(monkeypatch: pytest.MonkeyPatch) -> None:
    # An ordinary reporting failure must not prevent the cleanup it describes,
    # nor replace the primary error that cleanup ran beside.
    from parallax.core.db_port import _resource_logging as resource_logging

    def refuse(*_args: object, **_kwargs: object) -> None:
        raise RuntimeError("the logging configuration is broken")

    monkeypatch.setattr(resource_logging._LOGGER, "warning", refuse)  # pyright: ignore[reportPrivateUsage] - the restricted logger is module-private and is the seam this proves nothing reaches
    issue = CleanupIssue(phase="inspect", code="suspect", diagnostic=_issue())
    report_resource_issues("startup", Unrelinquished((issue,)))


class _NeverAcquires(ConnectsAsItself):
    """A double proving a path takes no connection, not merely that it runs no SQL."""

    dialect = ScriptedAdapter().dialect

    def open(self) -> Any:
        raise AssertionError("no runtime expected — this path opens no database")


def test_a_refused_query_reaches_no_runtime_at_all() -> None:
    with pytest.raises(Exception, match="snapshot-class-backed-model-required"):
        connect(_NeverAcquires(), "not a model")  # pyright: ignore[reportArgumentType] - the runtime refusal of an untyped caller is what this proves


def test_a_model_that_cannot_be_prepared_opens_no_runtime_at_all(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Preparation is the fallible half of judging a model, and it runs BEFORE
    # anything is opened: a model that could never be served costs no resource,
    # not merely no statement. The adapter here refuses to open at all, so
    # reaching it is the failure.
    from parallax.snapshot.handle import _database as database_module

    def refuse(*_args: object, **_kwargs: object) -> object:
        raise RuntimeError("this model cannot be prepared")

    monkeypatch.setattr(database_module, "prepare_model", refuse)

    with pytest.raises(RuntimeError, match="cannot be prepared"):
        connect(_NeverAcquires(), ACCOUNT, clock=FixedClock(FIXED))


def test_a_composition_that_fails_after_the_runtime_opened_closes_it_again(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # A refusal on the other side of the open closes what it took, so no
    # half-composed handle is published and the runtime is not left to a caller
    # that never received one. The refusal is injected into the demarcation the
    # handle composes, which is work that genuinely runs after opening.
    from parallax.snapshot.handle import _database as database_module

    def refuse(*_args: object, **_kwargs: object) -> object:
        raise RuntimeError("this handle cannot be composed")

    monkeypatch.setattr(database_module, "Demarcation", refuse)
    adapter = ScriptedAdapter()

    with pytest.raises(RuntimeError, match="cannot be composed"):
        connect(adapter, ACCOUNT, clock=FixedClock(FIXED))

    assert adapter.closes == 1


def test_participating_work_answers_the_attempts_connection_without_acquiring() -> None:
    # A stream inside a transaction is one more thing running on the attempt's
    # connection rather than a second borrower of it, so it acquires nothing and
    # releases nothing of its own.
    adapter = ScriptedAdapter(Transact(Read(rows=[_order_row(1)]), Read(rows=[])))
    with _db(adapter, ORDERS_MODEL) as db:

        def body(tx: Transaction) -> list[object]:
            with tx.stream(_orders_query(), batch_size=2) as roots:
                return list(roots)

        assert db.transact(body)

    assert (adapter.acquisitions, adapter.cleanups) == (1, [Returned()])
