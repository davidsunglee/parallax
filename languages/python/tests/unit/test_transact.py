"""`Database` demarcation unit tests (spec §5, Docker-free fake ports).

`Database.transact` composes M3's unit-of-work shell, increment 1's write
lowering, and the `m-auto-retry` bounded loop over an injected `m-db-port`:
commit and abort wiring, join semantics (same Transaction, option conflicts,
rollback-only foreclosure), withheld values on abort, and the retry
classification matrix — including the spec §5 requirement that a rollback-only
commit refusal keeps its original cause's retriability.

The keyed, predicate-selected, and read halves of the transaction surface moved
to `test_transaction_{writes,predicate_writes,reads}.py` in COR-42 Phase 5.
"""

from __future__ import annotations

import contextlib
from collections.abc import Callable
from decimal import Decimal

import pytest
from _transact_support import (
    ACCOUNT,
    FIXED,
    NEW_ROW,
    RecordingPort,
    account_db,
    deadlock,
    new_account,
)

import mirrored_models as mm
from parallax.core import opt_lock
from parallax.core.db_error import DatabaseError
from parallax.core.unit_work import (
    EscapedTransactionError,
    FixedClock,
    FlushPlan,
    RollbackOnlyError,
    TransactionSettings,
    UnitOfWork,
    UnitOfWorkError,
    run_unit_of_work,
)
from parallax.snapshot.handle import Database, Transaction, TransactionOptionConflictError

pytestmark = pytest.mark.unit


def test_abort_discards_the_buffer_and_withholds_the_value() -> None:
    port = RecordingPort()

    def fn(tx: Transaction) -> str:
        tx.insert(new_account())
        raise RuntimeError("boom")

    with pytest.raises(RuntimeError, match="boom"):
        account_db(port).transact(fn)
    # Nothing flushed: the buffered write never reached the port.
    assert port.ops == [("begin",), ("rollback",)]


def test_an_escaped_transaction_reference_raises_after_the_scope_ends() -> None:
    port = RecordingPort()
    escaped: list[Transaction] = []

    def fn(tx: Transaction) -> None:
        escaped.append(tx)

    account_db(port).transact(fn)
    with pytest.raises(EscapedTransactionError):
        escaped[0].insert(new_account())


# --------------------------------------------------------------------------- #
# Join semantics: same Transaction, option conflicts, foreclosure.             #
# --------------------------------------------------------------------------- #
def test_join_receives_the_same_transaction_and_returns_immediately() -> None:
    port = RecordingPort()
    db = account_db(port)

    def outer(tx: Transaction) -> int:
        inner = db.transact(lambda inner_tx: (inner_tx is tx, 42))
        assert inner == (True, 42)
        return inner[1]

    assert db.transact(outer) == 42
    assert port.begins == 1  # the join opened no second database transaction


def test_join_with_equal_or_omitted_options_inherits() -> None:
    port = RecordingPort()
    db = account_db(port)

    def outer(_tx: Transaction) -> str:
        # Explicit-and-equal to the resolved defaults: accepted, not a conflict.
        return db.transact(
            lambda _inner: "joined",
            retries=10,
            concurrency="locking",
            retry_optimistic_conflicts=False,
        )

    assert db.transact(outer) == "joined"


def _must_not_run(_tx: Transaction) -> None:  # pragma: no cover - conflict forecloses it
    raise AssertionError("the joined closure must not run on an option conflict")


_CONFLICTING_JOINS: list[tuple[str, Callable[[Database], object]]] = [
    ("retries", lambda db: db.transact(_must_not_run, retries=3)),
    ("concurrency", lambda db: db.transact(_must_not_run, concurrency="optimistic")),
    (
        "retry_optimistic_conflicts",
        lambda db: db.transact(_must_not_run, retry_optimistic_conflicts=True),
    ),
]


@pytest.mark.parametrize(("option", "join"), _CONFLICTING_JOINS)
def test_join_with_a_conflicting_explicit_option_raises(
    option: str, join: Callable[[Database], object]
) -> None:
    port = RecordingPort()
    db = account_db(port)

    def outer(_tx: Transaction) -> str:
        with pytest.raises(TransactionOptionConflictError, match=option):
            join(db)
        return "survived"

    # The conflict is refused before the joined closure runs, and refusing it
    # does not doom the outer transaction (nothing entered the joined frame).
    assert db.transact(outer) == "survived"


def test_joining_a_doomed_transaction_is_foreclosed_before_its_closure_runs() -> None:
    port = RecordingPort()
    db = account_db(port)
    ran: list[bool] = []

    def outer(_tx: Transaction) -> str:
        with pytest.raises(RuntimeError, match="inner failure"):
            db.transact(_raise_inner)
        with pytest.raises(RollbackOnlyError):
            db.transact(lambda _inner: ran.append(True))
        return "unreachable value"

    # The outer callback caught everything and returned normally, but the inner
    # failure doomed the transaction: commit is refused and the value withheld.
    with pytest.raises(RollbackOnlyError) as excinfo:
        db.transact(outer)
    assert isinstance(excinfo.value.__cause__, RuntimeError)
    assert ran == []
    assert port.ops == [("begin",), ("rollback",)]


def _raise_inner(_tx: Transaction) -> None:
    raise RuntimeError("inner failure")


def test_bare_unit_of_work_on_the_thread_is_refused() -> None:
    port = RecordingPort()
    db = account_db(port)

    def executor(_plan: FlushPlan) -> None:  # pragma: no cover - never flushed
        raise AssertionError("no flush expected")

    def body(_uow: UnitOfWork) -> None:
        with pytest.raises(UnitOfWorkError, match="bare unit of work"):
            db.transact(lambda _tx: None)

    run_unit_of_work(
        body,
        settings=TransactionSettings(),
        clock=FixedClock(FIXED),
        meta=ACCOUNT,
        flush_executor=executor,
    )


# --------------------------------------------------------------------------- #
# Bounded retry (m-auto-retry through db.transact).                            #
# --------------------------------------------------------------------------- #
def test_a_deadlock_is_retried_and_the_reexecution_succeeds() -> None:
    port = RecordingPort()
    port.txn_faults = [deadlock(), deadlock()]
    assert account_db(port).transact(lambda _tx: "ok") == "ok"
    assert port.begins == 3


def test_exhaustion_reraises_the_failure_with_the_attempt_count() -> None:
    port = RecordingPort()
    port.txn_faults = [deadlock(), deadlock(), deadlock()]
    with pytest.raises(DatabaseError) as excinfo:
        account_db(port).transact(lambda _tx: "ok", retries=2)
    assert port.begins == 3
    assert excinfo.value.is_retriable  # the surfaced error is the failure itself
    assert "3 attempts (retries=2)" in "".join(excinfo.value.__notes__)


def test_the_default_bound_is_ten_reexecutions() -> None:
    port = RecordingPort()
    port.txn_faults = [deadlock() for _ in range(11)]
    with pytest.raises(DatabaseError) as excinfo:
        account_db(port).transact(lambda _tx: "ok")
    assert port.begins == 11
    assert "11 attempts (retries=10)" in "".join(excinfo.value.__notes__)


@pytest.mark.parametrize(
    ("category", "native"),
    [("uniqueViolation", "23505"), ("lockWaitTimeout", "55P03")],
)
def test_non_retriable_categories_surface_after_one_attempt(category: str, native: str) -> None:
    port = RecordingPort()
    port.txn_faults = [DatabaseError(category=category, native_code=native, message=category)]  # type: ignore[arg-type]
    with pytest.raises(DatabaseError):
        account_db(port).transact(lambda _tx: "ok")
    assert port.begins == 1


def test_retries_zero_disables_the_loop() -> None:
    port = RecordingPort()
    port.txn_faults = [deadlock()]
    with pytest.raises(DatabaseError):
        account_db(port).transact(lambda _tx: "ok", retries=0)
    assert port.begins == 1


def test_negative_retries_are_rejected_before_any_attempt() -> None:
    port = RecordingPort()
    with pytest.raises(ValueError, match="retries must be >= 0"):
        account_db(port).transact(lambda _tx: "ok", retries=-1)
    assert port.begins == 0


def test_rollback_only_refusal_keeps_the_original_retriability() -> None:
    # Spec §5: an inner deadlock dooms the transaction; even though the outer
    # callback catches it and returns normally, the commit refusal preserves the
    # cause's classification — the retry loop re-executes, and the fresh attempt
    # succeeds.
    port = RecordingPort(rows=[NEW_ROW])
    port.read_faults = [deadlock()]
    db = account_db(port)

    def outer(_tx: Transaction) -> str:
        with contextlib.suppress(DatabaseError):
            db.transact(lambda inner_tx: inner_tx.find(mm.Account.where(mm.Account.id == 7)))
        return "caught"

    assert db.transact(outer) == "caught"
    assert port.begins == 2


# --------------------------------------------------------------------------- #
# Optimistic-lock conflict opt-in (m-opt-lock "Retry contract"; m-auto-retry, #
# COR-3 Phase 8 increment 6): `retry_optimistic_conflicts` joins             #
# `OptimisticLockConflictError` to the retriable set — the SAME `0`-then-`1`  #
# affected-rows transition `m-opt-lock-009` witnesses against real Postgres,  #
# reproduced here with a scripted `write_affected_queue` fake port.           #
# --------------------------------------------------------------------------- #
def _observe_and_update(tx: Transaction) -> None:
    current = tx.find(mm.Account.where(mm.Account.id == 3)).result()
    tx.update(current.model_copy(update={"balance": Decimal("20.00")}))


def test_optimistic_conflict_surfaces_after_one_attempt_without_the_opt_in() -> None:
    port = RecordingPort(rows=[{"id": 3, "owner": "Grace", "balance": 10.00, "version": 1}])
    port.write_affected_queue = [0]
    with pytest.raises(opt_lock.OptimisticLockConflictError):
        account_db(port).transact(_observe_and_update, concurrency="optimistic")
    assert port.begins == 1


def test_optimistic_conflict_is_auto_retried_to_success_with_the_opt_in() -> None:
    port = RecordingPort(rows=[{"id": 3, "owner": "Grace", "balance": 10.00, "version": 1}])
    port.write_affected_queue = [0, 1]
    account_db(port).transact(
        _observe_and_update, concurrency="optimistic", retry_optimistic_conflicts=True
    )
    assert port.begins == 2  # the conflicting attempt, then the retried (successful) attempt


def test_optimistic_conflict_opt_in_exhausts_its_bound() -> None:
    port = RecordingPort(rows=[{"id": 3, "owner": "Grace", "balance": 10.00, "version": 1}])
    port.write_affected_queue = [0, 0, 0]  # persistent — every attempt conflicts
    with pytest.raises(opt_lock.OptimisticLockConflictError) as excinfo:
        account_db(port).transact(
            _observe_and_update,
            concurrency="optimistic",
            retries=2,
            retry_optimistic_conflicts=True,
        )
    assert port.begins == 3
    assert "3 attempts (retries=2)" in "".join(excinfo.value.__notes__)


def test_optimistic_conflict_opt_in_is_inert_for_a_transient_failure() -> None:
    # The opt-in gates ONLY the conflict classification branch; a transient
    # database failure is retriable regardless of the flag's value (m-auto-retry
    # "Which failures are retriable" — transients are always retriable). This
    # RETRIABLE deadlock is classified retriable by `_retriable_failure` alone
    # (the `or`'s left operand), so it never actually reaches the opt-in's own
    # predicate at all — see the NON-retriable sibling below for that.
    port = RecordingPort()
    port.txn_faults = [deadlock()]
    assert account_db(port).transact(lambda _tx: "ok", retry_optimistic_conflicts=True) == "ok"
    assert port.begins == 2


def test_optimistic_conflict_opt_in_is_inert_for_a_non_retriable_database_error() -> None:
    # A NON-retriable `DatabaseError` (neither a direct
    # `OptimisticLockConflictError` nor a `RollbackOnlyError` wrapping one)
    # reaches the opt-in's own predicate (`_optimistic_conflict_retriable`,
    # since `_retriable_failure` alone already calls it non-retriable) and
    # is classified non-retriable there too — the opt-in's structural
    # extension never widens the retriable set beyond the optimistic-lock
    # conflict shape itself.
    port = RecordingPort()
    port.txn_faults = [
        DatabaseError(category="uniqueViolation", native_code="23505", message="dup")
    ]
    with pytest.raises(DatabaseError):
        account_db(port).transact(lambda _tx: "ok", retry_optimistic_conflicts=True)
    assert port.begins == 1


def test_optimistic_conflict_opt_in_is_inert_in_locking_mode() -> None:
    # Locking mode never gates a versioned UPDATE (`m-opt-lock` "the version
    # column" — the shared read lock, not a version check, is what makes the
    # write correct), so there is nothing for the opt-in to ever retry: a
    # single-attempt commit, `retry_optimistic_conflicts` notwithstanding.
    port = RecordingPort(rows=[{"id": 3, "owner": "Grace", "balance": 10.00, "version": 1}])
    account_db(port).transact(
        _observe_and_update, concurrency="locking", retry_optimistic_conflicts=True
    )
    assert port.begins == 1


def _observe_update_then_force_flush(tx: Transaction) -> None:
    current = tx.find(mm.Account.where(mm.Account.id == 3)).result()
    tx.update(current.model_copy(update={"balance": Decimal("20.00")}))
    tx.find(mm.Account.where(mm.Account.id == 3))  # forces the flush inside THIS (joined) scope


def test_optimistic_conflict_rollback_only_cause_is_retried_with_the_opt_in() -> None:
    # Spec §5's join rule extended to an optimistic-lock conflict (pinned
    # semantics #5): a JOINED scope's own conflict, discovered by its OWN
    # forced flush (read-your-own-writes), dooms the ROOT rollback-only; the
    # outer callback catches it and returns normally, but commit is refused —
    # the outermost retry loop still applies per the ORIGINAL failure's
    # category (the conflict, not a `DatabaseError`), retriable here because
    # the opt-in is set.
    port = RecordingPort(rows=[{"id": 3, "owner": "Grace", "balance": 10.00, "version": 1}])
    port.write_affected_queue = [0, 1]
    db = account_db(port)

    def outer(_tx: Transaction) -> str:
        with contextlib.suppress(opt_lock.OptimisticLockConflictError):
            db.transact(_observe_update_then_force_flush)  # joins; conflicts mid-scope
        return "caught"

    assert db.transact(outer, concurrency="optimistic", retry_optimistic_conflicts=True) == "caught"
    assert port.begins == 2  # the conflicting attempt, then the retried (successful) attempt
