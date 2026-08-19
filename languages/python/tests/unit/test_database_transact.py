"""`Database` demarcation unit tests (spec §5, Docker-free fake ports).

The observable behavior of `parallax.snapshot.handle._database`, driven entirely
through the public `Database` surface: `Database.transact` composes the
unit-of-work shell, write lowering, and the `m-auto-retry` bounded
loop over an injected `m-db-port` — commit and abort wiring, join semantics (same
Transaction, option conflicts, rollback-only foreclosure), withheld values on
abort, escaped transaction references, and the retry classification matrix,
including the spec §5 requirement that a rollback-only commit refusal keeps its
original cause's retriability.

Everything a `Transaction` itself does is elsewhere: keyed verbs in
`test_transaction_writes.py`, the `*_where` family in
`test_transaction_predicate_writes.py`, participating reads in
`test_transaction_reads.py`.
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
    PERSON,
    NoIoPort,
    RecordingPort,
    account_db,
    db_for,
    deadlock,
    new_account,
    read_account,
)

from _support import mirrored_models as mm
from _support.db_port import body_outcome
from _support.planner_probes import TEST_SUBJECT_IDENTITY
from parallax.core import Attr, DomainModel, Entity, Int32, attr, index
from parallax.core.db_error import DatabaseError
from parallax.core.db_port import DbPort, RollbackFailed, RolledBack, TransactionOutcome
from parallax.core.entity._model import model_of
from parallax.core.unit_work import (
    CardinalityCorruptionError,
    EscapedTransactionError,
    FixedClock,
    MissingTargetError,
    OptimisticLockConflictError,
    RollbackOnlyError,
    StaleWriteError,
    TransactionSettings,
    UnitOfWork,
    UnitOfWorkError,
    WriteBatchTrigger,
    WritePlan,
    run_unit_of_work,
)
from parallax.snapshot.handle import (
    Database,
    Transaction,
    TransactionOptionConflictError,
    TransactionOwnershipError,
    TransactionRollbackError,
    build_write_planner,
)


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
            concurrency="optimistic",
            retry_optimistic_conflicts=False,
        )

    assert db.transact(outer) == "joined"


def _must_not_run(_tx: Transaction) -> None:  # pragma: no cover - conflict forecloses it
    raise AssertionError("the joined closure must not run on an option conflict")


_CONFLICTING_JOINS: list[tuple[str, Callable[[Database], object]]] = [
    ("retries", lambda db: db.transact(_must_not_run, retries=3)),
    ("concurrency", lambda db: db.transact(_must_not_run, concurrency="locking")),
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


def test_a_non_transactional_find_opens_no_unit_of_work_to_participate_in() -> None:
    # `Database.find` is outside demarcation entirely: no `begin`, no `commit`,
    # and so no unit of work whose participation its values could carry. That is
    # the demarcation fact behind the read executor's own rule — a read with no
    # unit of work behind it stamps no participation and files into no index,
    # while the values it publishes still retain the state each row observed
    # (`test_transaction_reads.py` pins that half).
    port = RecordingPort(rows=[NEW_ROW])
    assert account_db(port).find(mm.Account.where(mm.Account.id == 7)).results() == [read_account()]
    assert [op[0] for op in port.ops] == ["read"]


def test_bare_unit_of_work_on_the_thread_is_refused() -> None:
    port = RecordingPort()
    db = account_db(port)

    def executor(  # pragma: no cover - never flushed
        _plan: WritePlan, *, trigger: WriteBatchTrigger
    ) -> None:
        raise AssertionError("no flush expected")

    def body(_uow: UnitOfWork) -> None:
        with pytest.raises(UnitOfWorkError, match="bare unit of work"):
            db.transact(lambda _tx: None)

    model = model_of(ACCOUNT)
    run_unit_of_work(
        body,
        settings=TransactionSettings(),
        clock=FixedClock(FIXED),
        meta=model,
        flush_executor=executor,
        planner=build_write_planner(model),
        subject_identity=TEST_SUBJECT_IDENTITY,
    )


# --------------------------------------------------------------------------- #
# Exact originating-Database ownership (ADR 0007): the demarcation records the  #
# exact `Database` that opened it, and a nested `transact` joins only through   #
# that object. Settled BEFORE everything the join section above pins.           #
# --------------------------------------------------------------------------- #
def test_an_alias_of_the_owner_joins_and_receives_the_identical_transaction() -> None:
    port = RecordingPort()
    db = account_db(port)
    alias = db  # a second name for one object — the only thing that ever joins

    def outer(tx: Transaction) -> int:
        assert alias.transact(lambda inner_tx: (inner_tx is tx, 42)) == (True, 42)
        return 42

    assert db.transact(outer) == 42
    assert port.begins == 1


def test_a_different_database_over_the_same_model_and_adapter_is_refused() -> None:
    port = RecordingPort()
    owner = account_db(port)
    foreign = account_db(port)  # same model, same adapter, same clock; a different object

    def outer(_tx: Transaction) -> str:
        with pytest.raises(TransactionOwnershipError) as excinfo:
            foreign.transact(_must_not_run)
        assert excinfo.value.code == "transaction-owner-mismatch"
        # Neither handle is retained: the refusal names no Database at all.
        assert repr(owner) not in str(excinfo.value)
        assert repr(foreign) not in str(excinfo.value)
        return "survived"

    # Refusing the join opened no second database transaction and did not doom
    # the outer one — nothing entered the joined frame.
    assert owner.transact(outer) == "survived"
    assert port.begins == 1


def _equal_account_model() -> DomainModel:
    """A model whose declarations are structurally equal to ``ACCOUNT``'s.

    A fresh class object per call is what makes the two models DISTINCT while
    their accepted Metamodels stay equal entity for entity — composing the same
    class twice would answer one model's classes from both and prove nothing
    about structural equality.
    """

    class Account(
        Entity,
        table="account",
        namespace="parallax.compatibility",
        indices=(index("account_owner", "owner"),),
    ):
        id: Attr[int] = attr(primary_key=True)
        owner: Attr[str] = attr(max_length=64)
        balance: Attr[Decimal] = attr(precision=18, scale=2)
        version: Attr[int] = attr(type=Int32, optimistic_locking=True)

    return DomainModel(Account)


def test_a_structurally_equal_model_establishes_no_ownership() -> None:
    port = RecordingPort()
    owner = account_db(port)
    foreign = db_for(_equal_account_model(), port)
    # The two accepted models are equal entity for entity, and that buys nothing.
    assert list(model_of(ACCOUNT).entities) == list(model_of(_equal_account_model()).entities)

    def outer(_tx: Transaction) -> str:
        with pytest.raises(TransactionOwnershipError):
            foreign.transact(_must_not_run)
        return "survived"

    assert owner.transact(outer) == "survived"


def test_the_ownership_refusal_reaches_no_adapter() -> None:
    port = NoIoPort()
    owner = Database.connect(port, ACCOUNT, clock=FixedClock(FIXED))
    foreign = Database.connect(port, ACCOUNT, clock=FixedClock(FIXED))

    def outer(_tx: Transaction) -> str:
        # `NoIoPort` raises on any read or write, so returning at all is the
        # proof that the refusal performed none.
        with pytest.raises(TransactionOwnershipError):
            foreign.transact(_must_not_run)
        return "survived"

    assert owner.transact(outer) == "survived"


def test_ownership_is_settled_before_rollback_only_and_option_conflicts() -> None:
    port = RecordingPort()
    owner = account_db(port)
    foreign = account_db(port)

    def outer(_tx: Transaction) -> str:
        # Doom the boundary, so rollback-only joining would refuse ANY join.
        with pytest.raises(RuntimeError, match="inner failure"):
            owner.transact(_raise_inner)
        # A foreign handle carrying a conflicting option: the doomed boundary
        # and the option conflict would each raise, and neither is the answer.
        with pytest.raises(TransactionOwnershipError):
            foreign.transact(_must_not_run, retries=3)
        # Nothing beyond the outer boundary's own `begin` ever reached the port.
        assert port.ops == [("begin",)]
        # Through the owner, the same conflicting option answers next…
        with pytest.raises(TransactionOptionConflictError, match="retries"):
            owner.transact(_must_not_run, retries=3)
        # …and with no option left to conflict, the doomed boundary answers last.
        with pytest.raises(RollbackOnlyError):
            owner.transact(_must_not_run)
        return "unreachable value"

    with pytest.raises(RollbackOnlyError):
        owner.transact(outer)
    assert port.ops == [("begin",), ("rollback",)]


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
    port.txn_faults = [DatabaseError(category=category, native_code=native, message=category)]  # type: ignore[arg-type] - parametrized str widens the DatabaseError category Literal
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
# Boundary outcomes (m-db-port / m-execution-lifecycle): which phase of the    #
# transaction failed decides what the caller sees and whether anything is      #
# re-executed, and only the composition root can reconcile the two.            #
# --------------------------------------------------------------------------- #
def _must_not_run_callback(_tx: Transaction) -> str:
    raise AssertionError("the callback runs only inside a transaction that began")


class _RollbackFailingPort(RecordingPort):
    """A port whose rollback never completes, however the transaction ended.

    The one boundary outcome no in-memory fake reaches by accident: the callback
    runs and whatever ended the transaction is reported beside a rollback failure
    of the port's own, exactly as a real adapter reports one when the connection
    is too broken to undo the work.
    """

    def __init__(self) -> None:
        super().__init__()
        self.rollback_error = DatabaseError(
            category=None, native_code=None, message="the connection is lost"
        )

    def transaction[T](self, body: Callable[[DbPort], T]) -> TransactionOutcome[T]:
        self.ops.append(("begin",))
        outcome = body_outcome(self, body)
        if isinstance(outcome, RolledBack):
            return RollbackFailed(outcome.trigger, self.rollback_error)
        self.ops.append(("commit",))
        return outcome


def test_a_boundary_that_never_began_surfaces_its_error_after_one_attempt() -> None:
    # No attempt ran, so there is nothing to re-execute — even though this error
    # would be retried on any attempt that had (m-execution-lifecycle: a begin
    # failure finishes the invocation with a direct, non-retryable failure).
    never_began = deadlock()
    port = RecordingPort()
    port.begin_faults = [never_began]
    with pytest.raises(DatabaseError) as excinfo:
        account_db(port).transact(_must_not_run_callback)
    assert excinfo.value is never_began
    assert port.begins == 1
    # The private carrier that made it terminal is not part of what a caller reads.
    assert excinfo.value.__suppress_context__


def test_a_failed_rollback_reports_both_live_errors_and_is_never_retried() -> None:
    # Retriable on its own, and still terminal: what the transaction left behind
    # is unknown, so re-executing it could double the work it may have committed.
    triggering = deadlock()

    def failing(_tx: Transaction) -> str:
        raise triggering

    port = _RollbackFailingPort()
    with pytest.raises(TransactionRollbackError) as excinfo:
        account_db(port).transact(failing)
    assert excinfo.value.triggering_error is triggering
    assert excinfo.value.rollback_error is port.rollback_error
    assert excinfo.value.__cause__ is port.rollback_error
    assert port.begins == 1


def test_a_failed_rollback_leaves_a_control_flow_trigger_primary() -> None:
    # An interrupt or a cancellation is not downgraded to an ordinary error: it
    # stays what the caller receives, carrying the rollback failure as its cause.
    interrupt = KeyboardInterrupt()

    def interrupted(_tx: Transaction) -> str:
        raise interrupt

    port = _RollbackFailingPort()
    with pytest.raises(KeyboardInterrupt) as excinfo:
        account_db(port).transact(interrupted)
    assert excinfo.value is interrupt
    assert excinfo.value.__cause__ is port.rollback_error


# --------------------------------------------------------------------------- #
# Optimistic-lock conflict opt-in (m-opt-lock "Retry contract";               #
# m-auto-retry): `retry_optimistic_conflicts` joins                           #
# `OptimisticLockConflictError` — and no other Write Effect Error — to the    #
# retriable set, the SAME `0`-then-`1` affected-rows transition               #
# `m-opt-lock-009` witnesses against real Postgres, reproduced here with a    #
# scripted `write_affected_queue` fake port.                                  #
# --------------------------------------------------------------------------- #
def _observe_and_update(tx: Transaction) -> None:
    current = tx.find(mm.Account.where(mm.Account.id == 3)).result()
    tx.update(current.edit(balance=Decimal("20.00")))


def test_optimistic_conflict_surfaces_after_one_attempt_without_the_opt_in() -> None:
    port = RecordingPort(
        rows=[{"id": 3, "owner": "Grace", "balance": Decimal("10.00"), "version": 1}]
    )
    port.write_affected_queue = [0]
    with pytest.raises(OptimisticLockConflictError):
        account_db(port).transact(_observe_and_update, concurrency="optimistic")
    assert port.begins == 1


def test_optimistic_conflict_is_auto_retried_to_success_with_the_opt_in() -> None:
    port = RecordingPort(
        rows=[{"id": 3, "owner": "Grace", "balance": Decimal("10.00"), "version": 1}]
    )
    port.write_affected_queue = [0, 1]
    account_db(port).transact(
        _observe_and_update, concurrency="optimistic", retry_optimistic_conflicts=True
    )
    assert port.begins == 2  # the conflicting attempt, then the retried (successful) attempt


def test_optimistic_conflict_opt_in_exhausts_its_bound() -> None:
    port = RecordingPort(
        rows=[{"id": 3, "owner": "Grace", "balance": Decimal("10.00"), "version": 1}]
    )
    port.write_affected_queue = [0, 0, 0]  # persistent — every attempt conflicts
    with pytest.raises(OptimisticLockConflictError) as excinfo:
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
    # RETRIABLE deadlock is classified retriable by `retriable_failure` alone
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
    # since `retriable_failure` alone already calls it non-retriable) and
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
    port = RecordingPort(
        rows=[{"id": 3, "owner": "Grace", "balance": Decimal("10.00"), "version": 1}]
    )
    account_db(port).transact(
        _observe_and_update, concurrency="locking", retry_optimistic_conflicts=True
    )
    assert port.begins == 1


# Every sibling below scripts `[0, 1]` (or `[2, 1]`): a second attempt WOULD
# have succeeded, so `begins == 1` is evidence the opt-in refused to widen
# rather than an artifact of a persistently failing port.
def test_stale_write_is_never_retried_even_with_the_opt_in() -> None:
    # A locking-mode versioned UPDATE renders no gate, so its zero-row shortfall
    # is the stale write: the shared read lock should have made it impossible,
    # which makes it a consistency failure no re-read resolves.
    port = RecordingPort(
        rows=[{"id": 3, "owner": "Grace", "balance": Decimal("10.00"), "version": 1}]
    )
    port.write_affected_queue = [0, 1]
    with pytest.raises(StaleWriteError):
        account_db(port).transact(
            _observe_and_update, concurrency="locking", retry_optimistic_conflicts=True
        )
    assert port.begins == 1


def _rename_person(tx: Transaction) -> None:
    fetched = tx.find(mm.Person.where(mm.Person.id == 1)).result()
    tx.update(fetched.edit(name="Grace"))


def test_missing_target_is_never_retried_even_with_the_opt_in() -> None:
    # An observation-free keyed write against an unversioned Entity: a shortfall
    # says only that the addressed rows are not there, and re-executing cannot
    # bring them into being. The renamed value comes from this transaction's own
    # read — an unversioned target needs no observation to WRITE, but every
    # keyed update needs a value some read of this store produced.
    port = RecordingPort(rows=[{"id": 1, "name": "Ada"}])
    port.write_affected_queue = [0, 1]
    with pytest.raises(MissingTargetError):
        db_for(PERSON, port).transact(_rename_person, retry_optimistic_conflicts=True)
    assert port.begins == 1


def test_cardinality_corruption_is_never_retried_even_with_the_opt_in() -> None:
    # An EXCESS over the exact count means an accepted identity, storage, or
    # lowering invariant does not hold — an invariant failure rather than a
    # concurrency outcome, so the opt-in never widens to it either.
    port = RecordingPort(
        rows=[{"id": 3, "owner": "Grace", "balance": Decimal("10.00"), "version": 1}]
    )
    port.write_affected_queue = [2, 1]
    with pytest.raises(CardinalityCorruptionError):
        account_db(port).transact(
            _observe_and_update, concurrency="optimistic", retry_optimistic_conflicts=True
        )
    assert port.begins == 1


def _observe_update_then_force_flush(tx: Transaction) -> None:
    current = tx.find(mm.Account.where(mm.Account.id == 3)).result()
    tx.update(current.edit(balance=Decimal("20.00")))
    tx.find(mm.Account.where(mm.Account.id == 3))  # forces the flush inside THIS (joined) scope


def test_optimistic_conflict_rollback_only_cause_is_retried_with_the_opt_in() -> None:
    # Spec §5's join rule extended to an optimistic-lock conflict (pinned
    # semantics #5): a JOINED scope's own conflict, discovered by its OWN
    # forced flush (read-your-own-writes), dooms the ROOT rollback-only; the
    # outer callback catches it and returns normally, but commit is refused —
    # the outermost retry loop still applies per the ORIGINAL failure's
    # category (the conflict, not a `DatabaseError`), retriable here because
    # the opt-in is set.
    port = RecordingPort(
        rows=[{"id": 3, "owner": "Grace", "balance": Decimal("10.00"), "version": 1}]
    )
    port.write_affected_queue = [0, 1]
    db = account_db(port)

    def outer(_tx: Transaction) -> str:
        with contextlib.suppress(OptimisticLockConflictError):
            db.transact(_observe_update_then_force_flush)  # joins; conflicts mid-scope
        return "caught"

    assert db.transact(outer, concurrency="optimistic", retry_optimistic_conflicts=True) == "caught"
    assert port.begins == 2  # the conflicting attempt, then the retried (successful) attempt
