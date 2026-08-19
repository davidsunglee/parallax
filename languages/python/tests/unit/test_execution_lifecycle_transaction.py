"""The Transaction Invocation Root Execution end to end (m-execution-lifecycle,
Docker-free).

One outer ``db.transact`` is one root spanning every physical attempt and every
joined invocation beneath it, so this is where the transaction topology is
graded: which activity is whose child, which attempt exists at all, which phase a
failure belongs to, and which already-finished activity a failure names as its
cause. Every assertion reads the events a Provider installed through ``connect``
actually received.

The port double reports outcomes rather than raising them, which is what makes
begin failure, commit failure, and rollback failure separable here at all — each
one is a different boundary phase, and the attempt activity says so.
"""

from __future__ import annotations

import gc
import weakref
from collections.abc import Callable, Sequence
from contextlib import suppress
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

import pytest
from _transact_support import (
    ACCOUNT,
    FIXED,
    NEW_ROW,
    RecordingPort,
    deadlock,
    new_account,
)

from _support import mirrored_models as mm
from _support.db_port import body_outcome
from parallax.core.db_error import DatabaseError
from parallax.core.db_port import DbPort, TransactionOutcome
from parallax.core.dialect import POSTGRES, Dialect
from parallax.core.execution_lifecycle import (
    AttemptCommitted,
    AttemptFailure,
    AttemptRollbackFailed,
    AttemptRolledBack,
    CausedFailure,
    DirectFailure,
    ExecutionEvent,
    JoinedInvocation,
    JoinedInvocationRaised,
    JoinedInvocationReturned,
    OuterInvocation,
    OuterInvocationCommitted,
    OuterInvocationFailed,
    ReadFailed,
    ReadFinished,
    ReadStarted,
    RetryPolicy,
    TransactionAttemptFinished,
    TransactionAttemptOutcome,
    TransactionAttemptStarted,
    TransactionInvocationFinished,
    TransactionInvocationOutcome,
    TransactionInvocationStarted,
    WriteBatchCompleted,
    WriteBatchFailed,
    WriteBatchFinished,
    WriteBatchStarted,
)
from parallax.core.execution_lifecycle.testing import RecordedRoot, RecordingLifecycleProvider
from parallax.core.object_query import deserialize as deserialize_query
from parallax.core.unit_work import (
    FixedClock,
    KeyedWrite,
    OptimisticLockConflictError,
    WritePlanningError,
)
from parallax.snapshot import connect
from parallax.snapshot.handle import Database, Transaction, TransactionRollbackError


def _db(port: DbPort, provider: Any, model: Any = ACCOUNT) -> Database:
    return connect(port, model, clock=FixedClock(FIXED), lifecycle_provider=provider)


def _transitions(events: Sequence[ExecutionEvent]) -> list[str]:
    return [type(event).__name__ for event in events]


def _tree(events: Sequence[ExecutionEvent]) -> list[tuple[str, int, int | None]]:
    return [(type(event).__name__, event.activity_id, event.parent_activity_id) for event in events]


def _only(recorder: RecordingLifecycleProvider) -> RecordedRoot:
    (root,) = recorder.roots
    assert root.execution.kind == "TRANSACTION_INVOCATION"
    # Correlation is contiguous and one-based on both counters for every root
    # this module drives, so each test below asserts shape rather than restating
    # the envelope's own contract.
    assert [event.sequence for event in root.events] == list(range(1, len(root.events) + 1))
    assert {event.execution_id for event in root.events} == {root.execution.id}
    return root


def _finished(root: RecordedRoot) -> TransactionInvocationOutcome:
    """The root activity's own terminal outcome, which is always its last event."""
    last = root.events[-1]
    assert isinstance(last, TransactionInvocationFinished)
    return last.outcome


def _attempt_outcomes(root: RecordedRoot) -> list[TransactionAttemptOutcome]:
    return [event.outcome for event in root.events if isinstance(event, TransactionAttemptFinished)]


def _increase_balance(tx: Transaction) -> None:
    """Read one Account and buffer a gated update of it — the shape that makes a
    zero-row write a shortfall the enforcer judges after the call completed."""
    account = tx.find(mm.Account.where(mm.Account.id == 7)).result()
    tx.update(account.edit(balance=Decimal("9.00")))


# --------------------------------------------------------------------------- #
# The committed topology.                                                      #
# --------------------------------------------------------------------------- #
def test_one_invocation_roots_its_attempt_its_batches_and_its_read() -> None:
    recorder = RecordingLifecycleProvider()
    port = RecordingPort(rows=[NEW_ROW])

    def body(tx: Transaction) -> str:
        tx.insert(new_account())
        tx.find(mm.Account.where(mm.Account.id == 7)).result()
        tx.insert(mm.Account(id=8, owner="Bell", balance=Decimal("1.00")))
        return "ok"

    assert _db(port, recorder).transact(body) == "ok"

    root = _only(recorder)
    # The dependency batch and the Read it enables are ordered SIBLINGS under the
    # attempt: the flush happens inside `uow.read`, before the Read opens, so
    # neither contains the other.
    assert _tree(root.events) == [
        ("TransactionInvocationStarted", 1, None),
        ("TransactionAttemptStarted", 2, 1),
        ("WriteBatchStarted", 3, 2),
        ("DatabaseCallStarted", 4, 3),
        ("DatabaseCallFinished", 4, 3),
        ("WriteBatchFinished", 3, 2),
        ("ReadStarted", 5, 2),
        ("DatabaseCallStarted", 6, 5),
        ("DatabaseCallFinished", 6, 5),
        ("ReadFinished", 5, 2),
        ("WriteBatchStarted", 7, 2),
        ("DatabaseCallStarted", 8, 7),
        ("DatabaseCallFinished", 8, 7),
        ("WriteBatchFinished", 7, 2),
        ("TransactionAttemptFinished", 2, 1),
        ("TransactionInvocationFinished", 1, None),
    ]
    started = root.events[0]
    assert isinstance(started, TransactionInvocationStarted)
    assert started.invocation == OuterInvocation("optimistic", RetryPolicy(10, False))
    assert _finished(root) == OuterInvocationCommitted()
    assert _attempt_outcomes(root) == [AttemptCommitted()]


def test_each_batch_names_the_trigger_that_forced_it() -> None:
    recorder = RecordingLifecycleProvider()
    port = RecordingPort(rows=[NEW_ROW])

    def body(tx: Transaction) -> None:
        tx.insert(new_account())
        tx.find(mm.Account.where(mm.Account.id == 7)).result()
        tx.insert(mm.Account(id=8, owner="Bell", balance=Decimal("1.00")))

    _db(port, recorder).transact(body)

    root = _only(recorder)
    batches = [event for event in root.events if isinstance(event, WriteBatchStarted)]
    assert [batch.trigger for batch in batches] == ["read_dependency", "pre_commit"]
    finished = [event for event in root.events if isinstance(event, WriteBatchFinished)]
    assert [batch.outcome for batch in finished] == [WriteBatchCompleted(), WriteBatchCompleted()]


def test_the_resolved_policy_the_caller_asked_for_is_what_the_invocation_reports() -> None:
    recorder = RecordingLifecycleProvider()
    _db(RecordingPort(), recorder).transact(
        lambda _tx: None, retries=3, concurrency="locking", retry_optimistic_conflicts=True
    )

    started = _only(recorder).events[0]
    assert isinstance(started, TransactionInvocationStarted)
    assert started.invocation == OuterInvocation("locking", RetryPolicy(3, True))


def test_an_empty_buffer_opens_no_write_batch_at_all() -> None:
    recorder = RecordingLifecycleProvider()
    _db(RecordingPort(rows=[NEW_ROW]), recorder).transact(
        lambda tx: tx.find(mm.Account.where(mm.Account.id == 7)).result()
    )

    root = _only(recorder)
    assert _transitions(root.events) == [
        "TransactionInvocationStarted",
        "TransactionAttemptStarted",
        "ReadStarted",
        "DatabaseCallStarted",
        "DatabaseCallFinished",
        "ReadFinished",
        "TransactionAttemptFinished",
        "TransactionInvocationFinished",
    ]


def test_a_row_form_read_is_a_child_of_the_attempt_under_the_rows_interface() -> None:
    recorder = RecordingLifecycleProvider()
    port = RecordingPort(rows=[NEW_ROW])
    query = deserialize_query(
        {"target": "Account", "predicate": {"eq": {"attr": "Account.id", "value": 7}}}
    )

    _db(port, recorder).transact(lambda tx: tx.read_rows(query))

    root = _only(recorder)
    read = root.events[2]
    assert isinstance(read, ReadStarted)
    assert (read.parent_activity_id, read.interface) == (2, "ROWS")


# --------------------------------------------------------------------------- #
# Retry: one root, many attempts.                                              #
# --------------------------------------------------------------------------- #
def test_a_retried_invocation_holds_both_attempts_under_one_root() -> None:
    recorder = RecordingLifecycleProvider()
    port = RecordingPort()
    port.txn_faults = [deadlock()]

    _db(port, recorder).transact(lambda tx: tx.insert(new_account()))

    root = _only(recorder)
    assert _transitions(root.events) == [
        "TransactionInvocationStarted",
        "TransactionAttemptStarted",
        "WriteBatchStarted",
        "DatabaseCallStarted",
        "DatabaseCallFinished",
        "WriteBatchFinished",
        "TransactionAttemptFinished",
        "TransactionAttemptStarted",
        "WriteBatchStarted",
        "DatabaseCallStarted",
        "DatabaseCallFinished",
        "WriteBatchFinished",
        "TransactionAttemptFinished",
        "TransactionInvocationFinished",
    ]
    # A retry re-executes the callback, so the second attempt runs its own batch
    # and its own call — every activity of the first is closed before it starts.
    rolled_back, committed = _attempt_outcomes(root)
    assert isinstance(rolled_back, AttemptRolledBack)
    assert (rolled_back.failure.phase, rolled_back.failure.retry_eligible) == ("COMMIT", True)
    assert committed == AttemptCommitted()
    assert _finished(root) == OuterInvocationCommitted()


def test_exhaustion_still_reports_the_classifier_truth_on_the_last_attempt() -> None:
    # `retry_eligible` is the verdict under the effective policy INDEPENDENT of
    # the budget: the attempt that ends the invocation was retriable and simply
    # had nothing left, which is a different fact from being non-retriable.
    recorder = RecordingLifecycleProvider()
    port = RecordingPort()
    port.txn_faults = [deadlock(), deadlock(), deadlock()]

    with pytest.raises(DatabaseError):
        _db(port, recorder).transact(lambda _tx: None, retries=2)

    root = _only(recorder)
    outcomes = _attempt_outcomes(root)
    assert len(outcomes) == 3
    assert all(
        isinstance(outcome, AttemptRolledBack) and outcome.failure.retry_eligible
        for outcome in outcomes
    )
    # Every attempt finished before the next one started, so no two attempts of
    # one invocation are ever open at the same time.
    assert _transitions(root.events) == [
        "TransactionInvocationStarted",
        *["TransactionAttemptStarted", "TransactionAttemptFinished"] * 3,
        "TransactionInvocationFinished",
    ]
    failed = _finished(root)
    assert isinstance(failed, OuterInvocationFailed)
    assert isinstance(failed.failure, CausedFailure)
    last_attempt = root.events[-2]
    assert failed.failure.cause_activity_id == last_attempt.activity_id


def test_the_opt_in_widens_the_verdict_the_attempt_reports() -> None:
    recorder = RecordingLifecycleProvider()
    port = RecordingPort(rows=[NEW_ROW])
    port.write_affected_queue = [0, 1]

    _db(port, recorder).transact(_increase_balance, retry_optimistic_conflicts=True)

    rolled_back, _committed = _attempt_outcomes(_only(recorder))
    assert isinstance(rolled_back, AttemptRolledBack)
    assert rolled_back.failure.retry_eligible


def test_without_the_opt_in_the_same_conflict_is_reported_non_eligible() -> None:
    recorder = RecordingLifecycleProvider()
    port = RecordingPort(rows=[NEW_ROW])
    port.write_affected_queue = [0, 1]

    with pytest.raises(OptimisticLockConflictError):
        _db(port, recorder).transact(_increase_balance)

    (rolled_back,) = _attempt_outcomes(_only(recorder))
    assert isinstance(rolled_back, AttemptRolledBack)
    assert not rolled_back.failure.retry_eligible


# --------------------------------------------------------------------------- #
# The boundary phases the port outcome separates.                              #
# --------------------------------------------------------------------------- #
def test_a_begin_failure_runs_no_attempt_and_fails_the_invocation_directly() -> None:
    recorder = RecordingLifecycleProvider()
    port = RecordingPort()
    port.begin_faults = [deadlock()]

    with pytest.raises(DatabaseError):
        _db(port, recorder).transact(lambda _tx: pytest.fail("the callback must never run"))

    root = _only(recorder)
    assert _transitions(root.events) == [
        "TransactionInvocationStarted",
        "TransactionInvocationFinished",
    ]
    failed = _finished(root)
    assert isinstance(failed, OuterInvocationFailed)
    # Direct rather than caused: there is no attempt activity for it to name, and
    # a retriable CATEGORY does not make an unattempted boundary retriable.
    assert isinstance(failed.failure, DirectFailure)
    assert failed.failure.diagnostic.qualified_type == "parallax.core.db_error.DatabaseError"
    assert port.begins == 1


def test_a_commit_failure_is_the_commit_phase() -> None:
    recorder = RecordingLifecycleProvider()
    port = RecordingPort()
    port.txn_faults = [DatabaseError(category="uniqueViolation", native_code="23505", message="d")]

    with pytest.raises(DatabaseError):
        _db(port, recorder).transact(lambda _tx: None)

    (rolled_back,) = _attempt_outcomes(_only(recorder))
    assert isinstance(rolled_back, AttemptRolledBack)
    assert rolled_back.failure.phase == "COMMIT"
    assert not rolled_back.failure.retry_eligible


def test_a_callback_failure_is_the_callback_phase() -> None:
    recorder = RecordingLifecycleProvider()

    def body(_tx: Transaction) -> None:
        raise ValueError("boom")

    with pytest.raises(ValueError, match="boom"):
        _db(RecordingPort(), recorder).transact(body)

    (rolled_back,) = _attempt_outcomes(_only(recorder))
    assert isinstance(rolled_back, AttemptRolledBack)
    assert rolled_back.failure.phase == "CALLBACK"
    assert isinstance(rolled_back.failure.failure, DirectFailure)


def test_a_failure_in_the_final_batch_is_the_pre_commit_phase() -> None:
    # The port reports one body failure however it arose, so the phase is decided
    # by exception identity against the pre-commit batch's own failure — not by
    # which half of the body happened to run last.
    recorder = RecordingLifecycleProvider()
    port = RecordingPort(rows=[NEW_ROW])
    port.write_affected_queue = [0]

    with pytest.raises(OptimisticLockConflictError):
        _db(port, recorder).transact(_increase_balance)

    (rolled_back,) = _attempt_outcomes(_only(recorder))
    assert isinstance(rolled_back, AttemptRolledBack)
    assert rolled_back.failure.phase == "PRE_COMMIT"


def test_a_failure_in_a_dependency_batch_is_still_the_callback_phase() -> None:
    # The dependency batch runs because the CALLBACK asked for a read, so a
    # failure inside it belongs to the callback: only the automatic batch after
    # the callback returned is the pre-commit phase.
    recorder = RecordingLifecycleProvider()
    port = RecordingPort(row_queue=[[NEW_ROW], [NEW_ROW]])
    port.write_affected_queue = [0]

    def body(tx: Transaction) -> None:
        _increase_balance(tx)
        tx.find(mm.Account.where(mm.Account.id == 7)).result()

    with pytest.raises(OptimisticLockConflictError):
        _db(port, recorder).transact(body)

    root = _only(recorder)
    batch = next(event for event in root.events if isinstance(event, WriteBatchStarted))
    assert batch.trigger == "read_dependency"
    (rolled_back,) = _attempt_outcomes(root)
    assert isinstance(rolled_back, AttemptRolledBack)
    assert rolled_back.failure.phase == "CALLBACK"


def test_a_rollback_failure_reports_both_live_failures() -> None:
    recorder = RecordingLifecycleProvider()
    port = RecordingPort()
    port.rollback_faults = [
        DatabaseError(category="connectionDead", native_code="08006", message="gone")
    ]

    def body(_tx: Transaction) -> None:
        raise ValueError("boom")

    with pytest.raises(TransactionRollbackError):
        _db(port, recorder).transact(body)

    root = _only(recorder)
    (outcome,) = _attempt_outcomes(root)
    assert isinstance(outcome, AttemptRollbackFailed)
    assert outcome.triggering_failure.phase == "CALLBACK"
    assert outcome.triggering_failure.failure.diagnostic.qualified_type == "builtins.ValueError"
    assert outcome.rollback_failure.qualified_type == "parallax.core.db_error.DatabaseError"
    # The invocation raises an error of its own rather than the trigger, so its
    # failure describes THAT error directly instead of naming an attempt whose
    # failure it does not describe.
    failed = _finished(root)
    assert isinstance(failed, OuterInvocationFailed)
    assert isinstance(failed.failure, DirectFailure)
    assert failed.failure.diagnostic.qualified_type.endswith("TransactionRollbackError")


def test_a_control_flow_escape_still_finishes_every_activity_it_left() -> None:
    recorder = RecordingLifecycleProvider()

    def body(_tx: Transaction) -> None:
        raise KeyboardInterrupt

    with pytest.raises(KeyboardInterrupt):
        _db(RecordingPort(), recorder).transact(body)

    root = _only(recorder)
    assert _transitions(root.events) == [
        "TransactionInvocationStarted",
        "TransactionAttemptStarted",
        "TransactionAttemptFinished",
        "TransactionInvocationFinished",
    ]
    (rolled_back,) = _attempt_outcomes(root)
    assert isinstance(rolled_back, AttemptRolledBack)
    assert rolled_back.failure.failure.diagnostic.qualified_type == "builtins.KeyboardInterrupt"
    assert not rolled_back.failure.retry_eligible


# --------------------------------------------------------------------------- #
# Joined invocations.                                                          #
# --------------------------------------------------------------------------- #
def test_a_joined_call_is_a_child_of_the_attempt_and_opens_no_attempt() -> None:
    recorder = RecordingLifecycleProvider()
    port = RecordingPort()
    db = _db(port, recorder)

    db.transact(lambda _outer: db.transact(lambda inner: inner.insert(new_account())))

    root = _only(recorder)
    # The joined activity runs no attempt of its own, and the write it buffered
    # reaches the OUTER attempt's pre-commit batch — a joined boundary adds no
    # third trigger.
    assert _tree(root.events) == [
        ("TransactionInvocationStarted", 1, None),
        ("TransactionAttemptStarted", 2, 1),
        ("TransactionInvocationStarted", 3, 2),
        ("TransactionInvocationFinished", 3, 2),
        ("WriteBatchStarted", 4, 2),
        ("DatabaseCallStarted", 5, 4),
        ("DatabaseCallFinished", 5, 4),
        ("WriteBatchFinished", 4, 2),
        ("TransactionAttemptFinished", 2, 1),
        ("TransactionInvocationFinished", 1, None),
    ]
    joined_started = root.events[2]
    assert isinstance(joined_started, TransactionInvocationStarted)
    assert joined_started.invocation == JoinedInvocation()
    joined_finished = root.events[3]
    assert isinstance(joined_finished, TransactionInvocationFinished)
    assert joined_finished.outcome == JoinedInvocationReturned()
    assert port.begins == 1


def test_a_joined_callback_that_raises_is_reported_as_raising_and_nothing_more() -> None:
    # Raised describes the nested callback alone: the physical transaction is
    # still the outer attempt's, and it is that attempt which reports the
    # rollback.
    recorder = RecordingLifecycleProvider()
    db = _db(RecordingPort(), recorder)

    def inner(_tx: Transaction) -> None:
        raise ValueError("nested")

    with pytest.raises(ValueError, match="nested"):
        db.transact(lambda _outer: db.transact(inner))

    root = _only(recorder)
    joined = root.events[3]
    assert isinstance(joined, TransactionInvocationFinished)
    assert isinstance(joined.outcome, JoinedInvocationRaised)
    assert joined.outcome.failure.diagnostic.qualified_type == "builtins.ValueError"
    (attempt,) = _attempt_outcomes(root)
    assert isinstance(attempt, AttemptRolledBack)
    # The attempt names the joined activity as its cause rather than rendering
    # the same exception a second time.
    assert isinstance(attempt.failure.failure, CausedFailure)
    assert attempt.failure.failure.cause_activity_id == joined.activity_id
    assert attempt.failure.failure.diagnostic is joined.outcome.failure.diagnostic


# --------------------------------------------------------------------------- #
# Causality.                                                                   #
# --------------------------------------------------------------------------- #
def test_a_zero_row_write_names_the_call_that_completed_as_the_cause() -> None:
    # The call reached the database and came back, so it COMPLETED; the shortfall
    # is judged afterwards and belongs to the batch. Attribution is by the
    # enforcement bracket rather than by which call ran last.
    recorder = RecordingLifecycleProvider()
    port = RecordingPort(rows=[NEW_ROW])
    port.write_affected_queue = [0]

    with pytest.raises(OptimisticLockConflictError):
        _db(port, recorder).transact(_increase_balance)

    root = _only(recorder)
    batch_finished = next(event for event in root.events if isinstance(event, WriteBatchFinished))
    call_finished = root.events[root.events.index(batch_finished) - 1]
    assert isinstance(batch_finished.outcome, WriteBatchFailed)
    failure = batch_finished.outcome.failure
    assert isinstance(failure, CausedFailure)
    assert failure.cause_activity_id == call_finished.activity_id
    assert failure.diagnostic.qualified_type.endswith("OptimisticLockConflictError")


def test_a_read_that_failed_is_what_its_attempt_names() -> None:
    recorder = RecordingLifecycleProvider()
    port = RecordingPort(rows=[NEW_ROW])
    port.read_faults = [deadlock()]

    with pytest.raises(DatabaseError):
        _db(port, recorder).transact(
            lambda tx: tx.find(mm.Account.where(mm.Account.id == 7)).result(), retries=0
        )

    root = _only(recorder)
    read_finished = root.events[5]
    assert isinstance(read_finished, ReadFinished)
    assert isinstance(read_finished.outcome, ReadFailed)
    (rolled_back,) = _attempt_outcomes(root)
    assert isinstance(rolled_back, AttemptRolledBack)
    assert isinstance(rolled_back.failure.failure, CausedFailure)
    # Each level names its own DIRECT child, and every level of the chain shares
    # the one diagnostic the failing call rendered.
    assert rolled_back.failure.failure.cause_activity_id == read_finished.activity_id
    assert rolled_back.failure.failure.diagnostic is read_finished.outcome.failure.diagnostic


def test_one_exception_raised_twice_names_the_read_that_is_still_propagating() -> None:
    # The same exception object reaches two reads: the callback handles the
    # first and lets the second escape. Identity alone cannot tell the two
    # occurrences apart, so the attempt must name the one unwinding through it
    # rather than the first on record.
    recorder = RecordingLifecycleProvider()
    port = RecordingPort(rows=[NEW_ROW])
    fault = deadlock()
    port.read_faults = [fault, fault]

    def body(tx: Transaction) -> None:
        with suppress(DatabaseError):
            tx.find(mm.Account.where(mm.Account.id == 7)).result()
        tx.find(mm.Account.where(mm.Account.id == 8)).result()

    with pytest.raises(DatabaseError):
        _db(port, recorder).transact(body, retries=0)

    root = _only(recorder)
    handled, escaping = (event for event in root.events if isinstance(event, ReadFinished))
    assert isinstance(escaping.outcome, ReadFailed)
    (rolled_back,) = _attempt_outcomes(root)
    assert isinstance(rolled_back, AttemptRolledBack)
    caused = rolled_back.failure.failure
    assert isinstance(caused, CausedFailure)
    assert caused.cause_activity_id == escaping.activity_id
    assert caused.cause_activity_id != handled.activity_id
    assert caused.diagnostic is escaping.outcome.failure.diagnostic


def test_a_join_the_failure_only_unwound_through_does_not_displace_the_read() -> None:
    # A joined invocation and the read inside it are SIBLINGS under the attempt,
    # and the join finishes last because it encloses the read. The attempt must
    # still name the read: the exception never stopped unwinding, so the join is
    # a scope it passed through rather than a later, independent failure.
    recorder = RecordingLifecycleProvider()
    port = RecordingPort(rows=[NEW_ROW])
    port.read_faults = [deadlock()]
    db = _db(port, recorder)

    def inner(tx: Transaction) -> None:
        tx.find(mm.Account.where(mm.Account.id == 7)).result()

    with pytest.raises(DatabaseError):
        db.transact(lambda _outer: db.transact(inner), retries=0)

    root = _only(recorder)
    assert _tree(root.events) == [
        ("TransactionInvocationStarted", 1, None),
        ("TransactionAttemptStarted", 2, 1),
        ("TransactionInvocationStarted", 3, 2),
        ("ReadStarted", 4, 2),
        ("DatabaseCallStarted", 5, 4),
        ("DatabaseCallFinished", 5, 4),
        ("ReadFinished", 4, 2),
        ("TransactionInvocationFinished", 3, 2),
        ("TransactionAttemptFinished", 2, 1),
        ("TransactionInvocationFinished", 1, None),
    ]
    read_finished = root.events[6]
    assert isinstance(read_finished, ReadFinished)
    assert isinstance(read_finished.outcome, ReadFailed)
    read_failure = read_finished.outcome.failure
    assert isinstance(read_failure, CausedFailure)
    assert read_failure.cause_activity_id == 5
    joined = root.events[7]
    assert isinstance(joined, TransactionInvocationFinished)
    assert isinstance(joined.outcome, JoinedInvocationRaised)
    # The join has no child of its own to name — the read it encloses is its
    # sibling — so its own failure is direct, but it renders nothing, reusing
    # the diagnostic already made.
    assert isinstance(joined.outcome.failure, DirectFailure)
    assert joined.outcome.failure.diagnostic is read_failure.diagnostic
    (rolled_back,) = _attempt_outcomes(root)
    assert isinstance(rolled_back, AttemptRolledBack)
    caused = rolled_back.failure.failure
    assert isinstance(caused, CausedFailure)
    assert caused.cause_activity_id == read_finished.activity_id
    assert caused.diagnostic is read_failure.diagnostic


def test_every_join_a_failure_unwound_through_leaves_the_read_named() -> None:
    # Two joins deep, so the enclosing scopes are passed through one after the
    # other: neither may take the attribution from the read, and neither may
    # render the exception a second time on the way out.
    recorder = RecordingLifecycleProvider()
    port = RecordingPort(rows=[NEW_ROW])
    port.read_faults = [deadlock()]
    db = _db(port, recorder)

    def innermost(tx: Transaction) -> None:
        tx.find(mm.Account.where(mm.Account.id == 7)).result()

    with pytest.raises(DatabaseError):
        db.transact(lambda _outer: db.transact(lambda _middle: db.transact(innermost)), retries=0)

    root = _only(recorder)
    read_finished = next(event for event in root.events if isinstance(event, ReadFinished))
    assert isinstance(read_finished.outcome, ReadFailed)
    diagnostic = read_finished.outcome.failure.diagnostic
    joins = [
        event.outcome
        for event in root.events
        if isinstance(event, TransactionInvocationFinished)
        and isinstance(event.outcome, JoinedInvocationRaised)
    ]
    assert len(joins) == 2
    assert all(join.failure.diagnostic is diagnostic for join in joins)
    (rolled_back,) = _attempt_outcomes(root)
    assert isinstance(rolled_back, AttemptRolledBack)
    caused = rolled_back.failure.failure
    assert isinstance(caused, CausedFailure)
    assert caused.cause_activity_id == read_finished.activity_id


def test_a_flush_that_dies_in_planning_is_a_batch_that_started_and_ran_nothing() -> None:
    # A Write Batch starts BEFORE planning precisely so a planning refusal is
    # attributable to the batch rather than to the callback around it.
    recorder = RecordingLifecycleProvider()
    port = RecordingPort()

    def body(tx: Transaction) -> None:
        tx._uow.buffer(  # pyright: ignore[reportPrivateUsage] - the only ingress that reaches an unplannable buffer
            KeyedWrite("insert", "Gadget", ({"id": 1, "name": "G"},))
        )

    with pytest.raises(WritePlanningError, match="Gadget"):
        _db(port, recorder).transact(body)

    root = _only(recorder)
    assert _transitions(root.events) == [
        "TransactionInvocationStarted",
        "TransactionAttemptStarted",
        "WriteBatchStarted",
        "WriteBatchFinished",
        "TransactionAttemptFinished",
        "TransactionInvocationFinished",
    ]
    batch = root.events[3]
    assert isinstance(batch, WriteBatchFinished)
    assert isinstance(batch.outcome, WriteBatchFailed)
    assert isinstance(batch.outcome.failure, DirectFailure)
    assert port.ops == [("begin",), ("rollback",)]


def test_a_failure_caught_and_re_raised_still_names_the_read_it_came_from() -> None:
    # A failure is the exception VALUE, so catching one, doing further work, and
    # re-raising it reports the Read the value came from rather than the callback
    # that performed the raise. This is the ordinary catch / clean up / re-raise
    # shape, and naming the child is what makes the chain worth walking.
    recorder = RecordingLifecycleProvider()
    port = RecordingPort(rows=[NEW_ROW])
    port.read_faults = [deadlock()]

    def body(tx: Transaction) -> None:
        with pytest.raises(DatabaseError) as caught:
            tx.find(mm.Account.where(mm.Account.id == 7)).result()
        tx.find(mm.Account.where(mm.Account.id == 8)).result()
        raise caught.value

    with pytest.raises(DatabaseError):
        _db(port, recorder).transact(body, retries=0)

    root = _only(recorder)
    failed_read, _later_read = (event for event in root.events if isinstance(event, ReadFinished))
    assert isinstance(failed_read.outcome, ReadFailed)
    (rolled_back,) = _attempt_outcomes(root)
    assert isinstance(rolled_back, AttemptRolledBack)
    assert rolled_back.failure.failure == CausedFailure(
        failed_read.outcome.failure.diagnostic, failed_read.activity_id
    )


def test_a_value_two_reads_produced_names_the_later_read_when_the_callback_re_raises() -> None:
    # The occurrence-level distinction the value rule gives up, pinned so it is
    # documented rather than discovered. One Dialect raises one PREALLOCATED
    # exception object, so two sibling Reads fail with the SAME value; the
    # callback catches both and raises that value a third time. Identity cannot
    # separate "the second Read is still unwinding" from "both were caught and
    # this is a third raise", so the attempt reports Caused naming the higher
    # Activity ID rather than Direct. Nothing inside Parallax reuses an exception
    # object, so only a caller-supplied extension can reach this.
    shared = ValueError("one planning failure, raised three times")

    @dataclass(frozen=True, slots=True)
    class _OneObjectDialect(Dialect):
        def quote(self, identifier: str) -> str:
            raise shared

    dialect = _OneObjectDialect(
        name=POSTGRES.name,
        reserved=POSTGRES.reserved,
        quote_char=POSTGRES.quote_char,
        error_codes=POSTGRES.error_codes,
    )
    recorder = RecordingLifecycleProvider()
    port = RecordingPort(rows=[NEW_ROW])

    def body(tx: Transaction) -> None:
        with suppress(ValueError):
            tx.find(mm.Account.where(mm.Account.id == 7)).result()
        with suppress(ValueError):
            tx.find(mm.Account.where(mm.Account.id == 8)).result()
        raise shared

    with pytest.raises(ValueError, match="raised three times"):
        connect(
            port,
            ACCOUNT,
            dialect=dialect,
            clock=FixedClock(FIXED),
            lifecycle_provider=recorder,
        ).transact(body, retries=0)

    root = _only(recorder)
    first_read, later_read = (event for event in root.events if isinstance(event, ReadFinished))
    assert first_read.activity_id < later_read.activity_id
    (rolled_back,) = _attempt_outcomes(root)
    assert isinstance(rolled_back, AttemptRolledBack)
    assert isinstance(rolled_back.failure.failure, CausedFailure)
    assert rolled_back.failure.failure.cause_activity_id == later_read.activity_id


def test_a_failure_stashed_past_a_later_one_is_reported_as_direct() -> None:
    # An activity keeps ONE attribution, handled or not, so a failure a caller
    # stashed past a later one is no longer attributable when it is re-raised.
    # The degradation is bounded and is the price of retaining one exception
    # graph rather than every failed child's: the attempt renders the re-raised
    # exception itself, and the read that first reported it still names it in
    # its own Finished event. Eviction is what buys that here — the two failures
    # are distinct objects, and identity is all the slot matches on.
    recorder = RecordingLifecycleProvider()
    port = RecordingPort(rows=[NEW_ROW])
    port.read_faults = [
        DatabaseError(category="deadlock", native_code="40P01", message="the stashed failure"),
        DatabaseError(category="deadlock", native_code="40P01", message="the later failure"),
    ]

    def body(tx: Transaction) -> None:
        with pytest.raises(DatabaseError) as stashed:
            tx.find(mm.Account.where(mm.Account.id == 7)).result()
        with suppress(DatabaseError):
            tx.find(mm.Account.where(mm.Account.id == 8)).result()
        raise stashed.value

    with pytest.raises(DatabaseError, match="the stashed failure"):
        _db(port, recorder).transact(body, retries=0)

    root = _only(recorder)
    stashed_read, _later_read = (event for event in root.events if isinstance(event, ReadFinished))
    assert isinstance(stashed_read.outcome, ReadFailed)
    assert isinstance(stashed_read.outcome.failure, CausedFailure)
    assert "the stashed failure" in stashed_read.outcome.failure.diagnostic.message
    (rolled_back,) = _attempt_outcomes(root)
    assert isinstance(rolled_back, AttemptRolledBack)
    assert rolled_back.failure.phase == "CALLBACK"
    assert isinstance(rolled_back.failure.failure, DirectFailure)
    assert "the stashed failure" in rolled_back.failure.failure.diagnostic.message


def test_a_join_re_raising_an_evicted_value_names_itself_rather_than_the_read() -> None:
    # Eviction decides which child a re-raise can name AT ALL, which is what
    # keeps the highest-ID rule from reaching back into history. The join
    # encloses two reads: the first fails with the value the join goes on to
    # re-raise, the second fails with a DIFFERENT one that takes the attempt's
    # slot. The first read's higher ID therefore stops being a candidate, and
    # the attempt names the join — the lower-numbered scope, because it is the
    # one that reported the value after the eviction. The join renders the
    # exception itself for the same reason: the attribution that would have lent
    # it the read's diagnostic is gone.
    recorder = RecordingLifecycleProvider()
    port = RecordingPort(rows=[NEW_ROW])
    port.read_faults = [
        DatabaseError(category="deadlock", native_code="40P01", message="the re-raised failure"),
        DatabaseError(category="deadlock", native_code="40P01", message="the evicting failure"),
    ]
    db = _db(port, recorder)

    def inner(tx: Transaction) -> None:
        with pytest.raises(DatabaseError) as first:
            tx.find(mm.Account.where(mm.Account.id == 7)).result()
        with suppress(DatabaseError):
            tx.find(mm.Account.where(mm.Account.id == 8)).result()
        raise first.value

    with pytest.raises(DatabaseError, match="the re-raised failure"):
        db.transact(lambda _outer: db.transact(inner), retries=0)

    root = _only(recorder)
    joined = next(
        event
        for event in root.events
        if isinstance(event, TransactionInvocationFinished)
        and isinstance(event.outcome, JoinedInvocationRaised)
    )
    assert isinstance(joined.outcome, JoinedInvocationRaised)
    re_raised_read, _evicting_read = (
        event for event in root.events if isinstance(event, ReadFinished)
    )
    assert joined.activity_id < re_raised_read.activity_id
    assert isinstance(re_raised_read.outcome, ReadFailed)
    assert isinstance(joined.outcome.failure, DirectFailure)
    assert joined.outcome.failure.diagnostic is not re_raised_read.outcome.failure.diagnostic
    assert "the re-raised failure" in joined.outcome.failure.diagnostic.message
    (rolled_back,) = _attempt_outcomes(root)
    assert isinstance(rolled_back, AttemptRolledBack)
    caused = rolled_back.failure.failure
    assert isinstance(caused, CausedFailure)
    assert caused.cause_activity_id == joined.activity_id
    assert caused.diagnostic is joined.outcome.failure.diagnostic


# --------------------------------------------------------------------------- #
# What a live activity keeps.                                                  #
# --------------------------------------------------------------------------- #
def test_an_attempt_keeps_one_handled_failure_however_many_it_sees() -> None:
    # Two hundred handled read failures, so a collection that grew with them
    # could not hide in any floor. A weak reference is the only instrument that
    # sees what a live activity still holds, and it reaches `DatabaseError`
    # because that is a Python class — a built-in exception supports none.
    handled = 200
    recorder = RecordingLifecycleProvider()
    port = RecordingPort(rows=[NEW_ROW])
    port.read_faults = [deadlock() for _ in range(handled)]
    watched: list[weakref.ref[DatabaseError]] = []

    def body(tx: Transaction) -> None:
        for _ in range(handled):
            try:
                tx.find(mm.Account.where(mm.Account.id == 7)).result()
            except DatabaseError as failure:
                watched.append(weakref.ref(failure))
        gc.collect()
        # The one still alive is the latest, held whether or not the caller
        # caught it, and its identity is the only one this attempt can still
        # attribute.
        assert [index for index, held in enumerate(watched) if held() is not None] == [handled - 1]

    _db(port, recorder).transact(body)

    assert len(watched) == handled
    gc.collect()
    assert all(held() is None for held in watched)


def test_an_invocation_keeps_one_failed_attempt_however_many_it_retries() -> None:
    # Every rolled-back attempt attributes its failure to the invocation, so the
    # invocation is the second place a per-event collection would grow — here
    # with the retry count rather than with the failures one attempt handled.
    recorder = RecordingLifecycleProvider()
    port = RecordingPort()
    watched: list[weakref.ref[DatabaseError]] = []

    def commit_failure() -> DatabaseError:
        failure = deadlock()
        watched.append(weakref.ref(failure))
        return failure

    port.txn_faults = [commit_failure(), commit_failure()]
    attempts = 0

    def body(tx: Transaction) -> None:
        nonlocal attempts
        attempts += 1
        if attempts == 3:
            gc.collect()
            assert [index for index, held in enumerate(watched) if held() is not None] == [1]
        tx.insert(new_account())

    _db(port, recorder).transact(body, retries=2)

    assert attempts == 3
    assert _finished(_only(recorder)) == OuterInvocationCommitted()
    gc.collect()
    assert all(held() is None for held in watched)


# --------------------------------------------------------------------------- #
# A port that breaks its own contract.                                         #
# --------------------------------------------------------------------------- #
class _AbandoningPort(RecordingPort):
    """A port that runs the body and then raises instead of reporting an outcome.

    Its contract forbids that, which is exactly why the attempt must survive it:
    balance is a property of the activity's shape, not of any port's discipline.
    """

    def transaction[T](self, body: Callable[[DbPort], T]) -> TransactionOutcome[T]:
        self.ops.append(("begin",))
        body_outcome(self, body)
        raise RuntimeError("the port gave up")


def test_an_attempt_is_finished_even_when_the_port_reports_no_outcome() -> None:
    recorder = RecordingLifecycleProvider()

    with pytest.raises(RuntimeError, match="the port gave up"):
        _db(_AbandoningPort(), recorder).transact(lambda _tx: None)

    root = _only(recorder)
    assert _transitions(root.events) == [
        "TransactionInvocationStarted",
        "TransactionAttemptStarted",
        "TransactionAttemptFinished",
        "TransactionInvocationFinished",
    ]
    (outcome,) = _attempt_outcomes(root)
    assert isinstance(outcome, AttemptRolledBack)
    assert isinstance(outcome.failure.failure, DirectFailure)
    assert outcome.failure == AttemptFailure(
        "CALLBACK", DirectFailure(outcome.failure.failure.diagnostic), False
    )
    assert outcome.failure.failure.diagnostic.qualified_type == "builtins.RuntimeError"


# --------------------------------------------------------------------------- #
# The unobserved and declined paths.                                           #
# --------------------------------------------------------------------------- #
def test_a_transaction_with_no_provider_installed_records_nothing() -> None:
    recorder = RecordingLifecycleProvider()
    port = RecordingPort(rows=[NEW_ROW])
    connect(port, ACCOUNT, clock=FixedClock(FIXED)).transact(_increase_balance)
    assert recorder.roots == ()


def test_a_declined_transaction_root_delivers_no_event() -> None:
    class _Declining:
        def open(self, execution: Any, /) -> None:
            del execution
            return None

        def report_handler_error(self, error: Any, /) -> None:  # pragma: no cover - never reported
            raise AssertionError(error)

    recorder = _Declining()
    port = RecordingPort(rows=[NEW_ROW])
    _db(port, recorder).transact(_increase_balance)
    assert port.ops[0] == ("begin",)


def test_the_attempt_started_transition_is_what_assigns_the_next_activity_id() -> None:
    # A boundary that never began consumes no activity ID, so the invocation's
    # own retry does not leave a gap nothing explains.
    recorder = RecordingLifecycleProvider()
    port = RecordingPort()
    port.begin_faults = [deadlock()]

    with pytest.raises(DatabaseError):
        _db(port, recorder).transact(lambda _tx: None)

    root = _only(recorder)
    assert [event.activity_id for event in root.events] == [1, 1]


def test_the_first_transition_a_joined_activity_makes_is_its_own_started() -> None:
    recorder = RecordingLifecycleProvider()
    db = _db(RecordingPort(), recorder)
    db.transact(lambda _outer: db.transact(lambda _inner: None))

    root = _only(recorder)
    assert [event.activity_id for event in root.events] == [1, 2, 3, 3, 2, 1]


def test_a_refused_join_opens_no_activity_at_all() -> None:
    # The deterministic refusals precede the joined activity exactly as public
    # preflight precedes a Read: a conflict reaches no transaction, so it is
    # observable only as the outer invocation's own failure.
    recorder = RecordingLifecycleProvider()
    db = _db(RecordingPort(), recorder)

    with pytest.raises(Exception, match="cannot join the active transaction"):
        db.transact(lambda _outer: db.transact(lambda _inner: None, retries=99))

    root = _only(recorder)
    assert _transitions(root.events) == [
        "TransactionInvocationStarted",
        "TransactionAttemptStarted",
        "TransactionAttemptFinished",
        "TransactionInvocationFinished",
    ]


def test_an_invalid_retry_bound_creates_no_root_and_reaches_no_provider() -> None:
    # `retries` is a public argument, so its bound belongs to the deterministic
    # preflight that precedes Root Execution creation: refusing it only at the
    # retry loop would call the Provider and publish the invocation's Started and
    # Finished first, and a Provider that fails on `open` would replace the
    # argument error the caller earned with one of its own.
    recorder = RecordingLifecycleProvider()
    port = RecordingPort()

    with pytest.raises(ValueError, match="retries must be >= 0"):
        _db(port, recorder).transact(_increase_balance, retries=-1)

    assert recorder.roots == ()
    assert port.ops == []


def test_the_attempt_started_transition_carries_only_its_correlation() -> None:
    recorder = RecordingLifecycleProvider()
    _db(RecordingPort(), recorder).transact(lambda _tx: None)

    started = _only(recorder).events[1]
    assert isinstance(started, TransactionAttemptStarted)
    assert (started.activity_id, started.parent_activity_id) == (2, 1)


# --------------------------------------------------------------------------- #
# Quarantine, from inside a transaction.                                       #
# --------------------------------------------------------------------------- #
class _QuarantiningHandler:
    """A Handler that fails ordinarily on the nth event it is given.

    Quarantine is delivery's own contract (`test_execution_lifecycle_delivery.py`
    grades that); what is graded here is the transaction it happens inside — the
    scopes an attempt, a batch, and a joined invocation still have to leave once
    nothing is listening.
    """

    def __init__(self, fail_at: int) -> None:
        self._fail_at = fail_at
        self.seen: list[ExecutionEvent] = []

    def handle(self, event: ExecutionEvent, /) -> None:
        self.seen.append(event)
        if len(self.seen) == self._fail_at:
            raise RuntimeError("the exporter queue is full")


class _SingleHandlerProvider:
    """A Provider answering one prepared Handler and recording its reports."""

    def __init__(self, handler: _QuarantiningHandler) -> None:
        self._handler = handler
        self.reported: list[object] = []

    def open(self, execution: object, /) -> _QuarantiningHandler:
        del execution
        return self._handler

    def report_handler_error(self, error: object, /) -> None:
        self.reported.append(error)


def _quarantined_at(fail_at: int) -> tuple[_QuarantiningHandler, _SingleHandlerProvider]:
    handler = _QuarantiningHandler(fail_at)
    return handler, _SingleHandlerProvider(handler)


def test_a_handler_quarantined_at_the_root_leaves_every_later_scope_silent() -> None:
    handler, provider = _quarantined_at(1)
    port = RecordingPort(rows=[NEW_ROW])

    # A dependency batch, a Read, and a pre-commit batch would all open here, and
    # a scope that finds delivery dead does the rest of its lifecycle work not at
    # all rather than doing it and dropping the result.
    assert _db(port, provider).transact(_increase_balance) is None
    assert _transitions(handler.seen) == ["TransactionInvocationStarted"]
    assert len(provider.reported) == 1
    assert port.ops[0] == ("begin",)
    assert port.ops[-1] == ("commit",)


def test_a_handler_quarantined_inside_a_batch_still_leaves_the_batch() -> None:
    handler, provider = _quarantined_at(3)  # invocation, attempt, then the batch
    port = RecordingPort(rows=[NEW_ROW])

    _db(port, provider).transact(lambda tx: tx.insert(new_account()))

    assert _transitions(handler.seen) == [
        "TransactionInvocationStarted",
        "TransactionAttemptStarted",
        "WriteBatchStarted",
    ]
    assert port.ops[-1] == ("commit",)


def test_a_handler_quarantined_inside_a_joined_call_still_leaves_it() -> None:
    handler, provider = _quarantined_at(3)  # invocation, attempt, then the join
    port = RecordingPort()
    db = _db(port, provider)

    db.transact(lambda _outer: db.transact(lambda _inner: None))

    assert _transitions(handler.seen) == [
        "TransactionInvocationStarted",
        "TransactionAttemptStarted",
        "TransactionInvocationStarted",
    ]
    assert port.ops == [("begin",), ("commit",)]


def test_a_join_that_opens_after_quarantine_opens_nothing() -> None:
    handler, provider = _quarantined_at(2)  # invocation, then the attempt
    port = RecordingPort()
    db = _db(port, provider)

    db.transact(lambda _outer: db.transact(lambda _inner: None))

    assert _transitions(handler.seen) == [
        "TransactionInvocationStarted",
        "TransactionAttemptStarted",
    ]
    assert port.ops == [("begin",), ("commit",)]
