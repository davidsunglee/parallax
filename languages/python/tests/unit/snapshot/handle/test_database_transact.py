"""`Database` transaction runner unit tests (spec §§3, 5, Docker-free fake ports).

The observable behavior of `parallax.snapshot.handle._transaction_runner`,
driven entirely through the public `Database` surface: `Database.transact`
composes the unit-of-work shell, write lowering, and the `m-auto-retry` bounded
loop over an injected `m-db-port` — commit and abort wiring, join semantics
(same Transaction, option conflicts, rollback-only foreclosure), resolution of
omitted options against the root's `DatabaseOptions` and inspection of the
resolved record, withheld values on
abort, escaped transaction references, the retry classification matrix,
including the spec §5 requirement that a rollback-only commit refusal keeps its
original cause's retriability, and the adoption every attempt makes from the
Serving Model: which edition a transaction, a join, a retry, and a failure
report, and what stays on its own type because it happened before adoption.

Everything a `Transaction` itself does is elsewhere: keyed verbs in
`test_transaction_writes.py`, the `*_where` family in
`test_transaction_predicate_writes.py`, participating reads in
`test_transaction_reads.py`.
"""

from __future__ import annotations

import contextlib
from collections.abc import Callable
from decimal import Decimal
from typing import Any, cast

import pytest

from parallax.core import Attr, DomainModel, Entity, Int32, attr, index
from parallax.core.db_error import DatabaseError
from parallax.core.db_port import (
    ISOLATION_LEVELS,
    DatabaseAdapter,
    DatabaseConnection,
    IsolationLevel,
    RollbackFailed,
    RolledBack,
    TransactionOutcome,
)
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
from parallax.snapshot import DatabaseOptions, ExecutionFailure, ServingModel, prepare_model
from parallax.snapshot.handle import (
    Database,
    Transaction,
    TransactionOptionConflictError,
    TransactionOwnershipError,
    TransactionRollbackError,
    build_write_planner,
)
from tests._support import mirrored_models as mm
from tests._support.adoption import raises_contextualized
from tests._support.db_port import (
    BeginCall,
    CommitCall,
    Read,
    ReadCall,
    RollbackCall,
    ScriptedAdapter,
    Transact,
    Write,
    body_outcome,
)
from tests._support.planner_probes import TEST_SUBJECT_IDENTITY
from tests.unit._transact_support import (
    ACCOUNT,
    FIXED,
    NEW_ROW,
    PERSON,
    account_db,
    db_for,
    deadlock,
    new_account,
    read_account,
)


def test_abort_discards_the_buffer_and_withholds_the_value() -> None:
    port = ScriptedAdapter(Transact())

    def fn(tx: Transaction) -> str:
        tx.insert(new_account())
        raise RuntimeError("boom")

    with raises_contextualized(RuntimeError, match="boom"):
        account_db(port).transact(fn)
    # Nothing flushed: the buffered write never reached the port.
    assert port.calls == [BeginCall(), RollbackCall()]


def test_an_escaped_transaction_reference_raises_after_the_scope_ends() -> None:
    port = ScriptedAdapter(Transact())
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
    port = ScriptedAdapter(Transact())
    db = account_db(port)

    def outer(tx: Transaction) -> int:
        inner = db.transact(lambda inner_tx: (inner_tx is tx, 42))
        assert inner == (True, 42)
        return inner[1]

    assert db.transact(outer) == 42
    assert port.calls.count(BeginCall()) == 1  # the join opened no second database transaction


def test_join_with_equal_or_omitted_options_inherits() -> None:
    port = ScriptedAdapter(Transact())
    db = account_db(port)

    def outer(_tx: Transaction) -> str:
        # Explicit-and-equal to the resolved defaults: accepted, not a conflict.
        return db.transact(
            lambda _inner: "joined",
            max_retries=10,
            concurrency="optimistic",
            retry_optimistic_conflicts=False,
            isolation="read_committed",
        )

    assert db.transact(outer) == "joined"


def _must_not_run(_tx: Transaction) -> None:  # pragma: no cover - conflict forecloses it
    raise AssertionError("the joined closure must not run on an option conflict")


_CONFLICTING_JOINS: list[tuple[str, Callable[[Database], object]]] = [
    ("max_retries", lambda db: db.transact(_must_not_run, max_retries=3)),
    ("concurrency", lambda db: db.transact(_must_not_run, concurrency="locking")),
    (
        "retry_optimistic_conflicts",
        lambda db: db.transact(_must_not_run, retry_optimistic_conflicts=True),
    ),
    # The transaction these join resolved the root's Read Committed, so NAMING
    # a different level conflicts on the same terms as the other three.
    ("isolation", lambda db: db.transact(_must_not_run, isolation="serializable")),
]


@pytest.mark.parametrize(("option", "join"), _CONFLICTING_JOINS)
def test_join_with_a_conflicting_explicit_option_raises(
    option: str, join: Callable[[Database], object]
) -> None:
    port = ScriptedAdapter(Transact())
    db = account_db(port)

    def outer(_tx: Transaction) -> str:
        with pytest.raises(TransactionOptionConflictError, match=option):
            join(db)
        return "survived"

    # The conflict is refused before the joined closure runs, and refusing it
    # does not doom the outer transaction (nothing entered the joined frame).
    assert db.transact(outer) == "survived"


# --------------------------------------------------------------------------- #
# Isolation: a closed vocabulary, refused here and mapped by the adapter.      #
# --------------------------------------------------------------------------- #
def test_an_omitted_isolation_asks_the_port_for_the_roots_read_committed() -> None:
    # Omission resolves to the root's default, and an unconfigured root's is a
    # concrete Read Committed: the port is asked for that level rather than for
    # nothing, so a database configured with a stronger default still opens
    # this boundary at the level Parallax resolved.
    port = ScriptedAdapter(Transact())
    account_db(port).transact(lambda _tx: "ok")
    assert port.calls == [BeginCall("read_committed"), CommitCall()]


@pytest.mark.parametrize("level", sorted(ISOLATION_LEVELS))
def test_every_level_of_the_vocabulary_reaches_the_port(level: str) -> None:
    # Every member of the closed vocabulary crosses the seam, and crosses it as
    # itself: the handle refuses what is outside the vocabulary and interprets
    # nothing inside it, leaving the mapping to the adapter that owns an engine.
    port = ScriptedAdapter(Transact())
    account_db(port).transact(lambda _tx: "ok", isolation=cast("IsolationLevel", level))
    assert port.calls == [BeginCall(cast("IsolationLevel", level)), CommitCall()]


@pytest.mark.parametrize(
    "level", ["read uncommitted", "repeatable read", "SERIALIZABLE", "", 3, None.__class__, None]
)
def test_a_level_outside_the_vocabulary_is_refused_before_the_port_is_asked(level: object) -> None:
    # A name outside the vocabulary names no guarantee any adapter could map, so
    # it is the caller's mistake rather than a database's refusal: raised where a
    # negative retry bound is, before anything opens. An engine's own spelling of
    # a level Parallax does carry is refused on the same terms as a level it does
    # not — being spelled for one database is what makes it unportable — and so
    # is `None`, which is an invalid value rather than a second spelling of
    # omission.
    port = ScriptedAdapter()
    with pytest.raises(ValueError, match="isolation must be one of"):
        account_db(port).transact(_must_not_run, isolation=cast("Any", level))
    assert port.calls == []


def test_a_joined_call_naming_a_level_outside_the_vocabulary_is_refused_as_invalid() -> None:
    # The refusal precedes the join comparison, so what a caller is told is that
    # the level does not exist — never that it disagrees with the active
    # boundary, which would read as though spelling it correctly would have been
    # accepted when the same level was already active.
    port = ScriptedAdapter(Transact())
    db = account_db(port)

    def outer(_tx: Transaction) -> str:
        with pytest.raises(ValueError, match="isolation must be one of") as refusal:
            db.transact(_must_not_run, isolation=cast("Any", "repeatable read"))
        assert not isinstance(refusal.value, TransactionOptionConflictError)
        return "survived"

    assert db.transact(outer, isolation="repeatable_read") == "survived"
    assert port.calls == [BeginCall("repeatable_read"), CommitCall()]


def test_every_retry_of_one_invocation_opens_at_the_requested_isolation() -> None:
    # The level belongs to the invocation rather than to one physical attempt:
    # a re-executed callback that silently ran at the database's default would
    # answer differently from the attempt before it.
    port = ScriptedAdapter(Transact(commit=deadlock()), Transact(commit=deadlock()), Transact())
    assert account_db(port).transact(lambda _tx: "ok", isolation="serializable") == "ok"
    assert port.calls.count(BeginCall("serializable")) == 3


def test_a_join_omitting_or_repeating_the_active_isolation_is_accepted() -> None:
    port = ScriptedAdapter(Transact())
    db = account_db(port)

    def outer(_tx: Transaction) -> str:
        assert db.transact(lambda _inner: "omitted") == "omitted"
        return db.transact(lambda _inner: "repeated", isolation="serializable")

    assert db.transact(outer, isolation="serializable") == "repeated"
    # Two joins, and neither opened a second boundary to re-negotiate.
    assert port.calls == [BeginCall("serializable"), CommitCall()]


def test_a_join_naming_a_different_isolation_raises_before_its_callback_runs() -> None:
    port = ScriptedAdapter(Transact())
    db = account_db(port)

    def outer(_tx: Transaction) -> str:
        with pytest.raises(TransactionOptionConflictError, match="isolation"):
            db.transact(_must_not_run, isolation="repeatable_read")
        return "survived"

    assert db.transact(outer, isolation="serializable") == "survived"


def test_joining_a_doomed_transaction_is_foreclosed_before_its_closure_runs() -> None:
    port = ScriptedAdapter(Transact())
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
    with raises_contextualized(RollbackOnlyError) as excinfo:
        db.transact(outer)
    assert isinstance(excinfo.value.__cause__, RuntimeError)
    assert ran == []
    assert port.calls == [BeginCall(), RollbackCall()]


def _raise_inner(_tx: Transaction) -> None:
    raise RuntimeError("inner failure")


def test_a_non_transactional_find_opens_no_unit_of_work_to_participate_in() -> None:
    # `Database.find` is outside demarcation entirely: no `begin`, no `commit`,
    # and so no unit of work whose participation its values could carry. That is
    # the demarcation fact behind the read executor's own rule — a read with no
    # unit of work behind it stamps no participation and files into no index,
    # while the values it publishes still retain the state each row observed
    # (`test_transaction_reads.py` pins that half).
    port = ScriptedAdapter(Read(rows=[NEW_ROW]))
    assert account_db(port).find(mm.Account.where(mm.Account.id == 7)).results() == [read_account()]
    assert [type(op) for op in port.calls] == [ReadCall]


def test_bare_unit_of_work_on_the_thread_is_refused() -> None:
    port = ScriptedAdapter()
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
    port = ScriptedAdapter(Transact())
    db = account_db(port)
    alias = db  # a second name for one object — the only thing that ever joins

    def outer(tx: Transaction) -> int:
        assert alias.transact(lambda inner_tx: (inner_tx is tx, 42)) == (True, 42)
        return 42

    assert db.transact(outer) == 42
    assert port.calls.count(BeginCall()) == 1


def test_a_different_database_over_the_same_model_and_adapter_is_refused() -> None:
    port = ScriptedAdapter(Transact())
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
    assert port.calls.count(BeginCall()) == 1


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
    port = ScriptedAdapter(Transact())
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
    port = ScriptedAdapter(Transact())
    owner = Database.connect(port, ACCOUNT, clock=FixedClock(FIXED))
    foreign = Database.connect(port, ACCOUNT, clock=FixedClock(FIXED))

    def outer(_tx: Transaction) -> str:
        # The boundary's script holds no statement, so returning at all is the
        # proof that the refusal performed none.
        with pytest.raises(TransactionOwnershipError):
            foreign.transact(_must_not_run)
        return "survived"

    assert owner.transact(outer) == "survived"


def test_ownership_is_settled_before_rollback_only_and_option_conflicts() -> None:
    port = ScriptedAdapter(Transact())
    owner = account_db(port)
    foreign = account_db(port)

    def outer(_tx: Transaction) -> str:
        # Doom the boundary, so rollback-only joining would refuse ANY join.
        with pytest.raises(RuntimeError, match="inner failure"):
            owner.transact(_raise_inner)
        # A foreign handle carrying a conflicting option: the doomed boundary
        # and the option conflict would each raise, and neither is the answer.
        with pytest.raises(TransactionOwnershipError):
            foreign.transact(_must_not_run, max_retries=3)
        # Nothing beyond the outer boundary's own `begin` ever reached the port.
        assert port.calls == [BeginCall()]
        # Through the owner, the same conflicting option answers next…
        with pytest.raises(TransactionOptionConflictError, match="max_retries"):
            owner.transact(_must_not_run, max_retries=3)
        # …and with no option left to conflict, the doomed boundary answers last.
        with pytest.raises(RollbackOnlyError):
            owner.transact(_must_not_run)
        return "unreachable value"

    with raises_contextualized(RollbackOnlyError):
        owner.transact(outer)
    assert port.calls == [BeginCall(), RollbackCall()]


# --------------------------------------------------------------------------- #
# Bounded retry (m-auto-retry through db.transact).                            #
# --------------------------------------------------------------------------- #
def test_a_deadlock_is_retried_and_the_reexecution_succeeds() -> None:
    port = ScriptedAdapter(Transact(commit=deadlock()), Transact(commit=deadlock()), Transact())
    assert account_db(port).transact(lambda _tx: "ok") == "ok"
    assert port.calls.count(BeginCall()) == 3


def test_exhaustion_reraises_the_failure_with_the_attempt_count() -> None:
    port = ScriptedAdapter(*(Transact(commit=deadlock()) for _ in range(3)))
    with raises_contextualized(DatabaseError) as excinfo:
        account_db(port).transact(lambda _tx: "ok", max_retries=2)
    assert port.calls.count(BeginCall()) == 3
    assert excinfo.value.is_retriable  # the surfaced error is the failure itself
    # The core loop's own note spells the bound by its own parameter name; the
    # public keyword that supplied the number is `max_retries`.
    assert "3 attempts (retries=2)" in "".join(excinfo.value.__notes__)


def test_the_default_bound_is_ten_reexecutions() -> None:
    port = ScriptedAdapter(*(Transact(commit=deadlock()) for _ in range(11)))
    with raises_contextualized(DatabaseError) as excinfo:
        account_db(port).transact(lambda _tx: "ok")
    assert port.calls.count(BeginCall()) == 11
    assert "11 attempts (retries=10)" in "".join(excinfo.value.__notes__)


@pytest.mark.parametrize(
    ("category", "native"),
    [("uniqueViolation", "23505"), ("lockWaitTimeout", "55P03")],
)
def test_non_retriable_categories_surface_after_one_attempt(category: str, native: str) -> None:
    port = ScriptedAdapter(
        Transact(
            commit=DatabaseError(category=category, native_code=native, message=category)  # type: ignore[arg-type] - parametrized str widens the DatabaseError category Literal
        )
    )
    with raises_contextualized(DatabaseError):
        account_db(port).transact(lambda _tx: "ok")
    assert port.calls.count(BeginCall()) == 1


def test_retries_zero_disables_the_loop() -> None:
    port = ScriptedAdapter(Transact(commit=deadlock()))
    with raises_contextualized(DatabaseError):
        account_db(port).transact(lambda _tx: "ok", max_retries=0)
    assert port.calls.count(BeginCall()) == 1


def test_negative_retries_are_rejected_before_any_attempt() -> None:
    port = ScriptedAdapter()
    with pytest.raises(ValueError, match="max_retries must be >= 0"):
        account_db(port).transact(lambda _tx: "ok", max_retries=-1)
    assert port.calls.count(BeginCall()) == 0


@pytest.mark.parametrize(
    ("keyword", "value", "message"),
    [
        ("max_retries", True, "max_retries must be a nonnegative int"),
        ("max_retries", 1.5, "max_retries must be a nonnegative int"),
        ("max_retries", None, "max_retries must be a nonnegative int"),
        ("concurrency", "pessimistic", "concurrency must be one of"),
        ("concurrency", None, "concurrency must be one of"),
        ("retry_optimistic_conflicts", 1, "retry_optimistic_conflicts must be a bool"),
        ("retry_optimistic_conflicts", None, "retry_optimistic_conflicts must be a bool"),
    ],
)
def test_an_explicit_value_outside_its_fields_contract_is_refused_before_any_attempt(
    keyword: str, value: object, message: str
) -> None:
    # Every explicit keyword is held to its field's contract — the same one the
    # root record enforces — and `None` is an invalid value for each rather than
    # a second spelling of omission. Refused before anything opens, as a bad
    # level is.
    port = ScriptedAdapter()
    with pytest.raises(ValueError, match=message):
        account_db(port).transact(_must_not_run, **cast("dict[str, Any]", {keyword: value}))
    assert port.calls == []


@pytest.mark.parametrize(
    ("keyword", "value", "message"),
    [
        ("max_retries", True, "max_retries must be a nonnegative int"),
        ("max_retries", -1, "max_retries must be >= 0"),
        ("concurrency", "pessimistic", "concurrency must be one of"),
        ("retry_optimistic_conflicts", None, "retry_optimistic_conflicts must be a bool"),
        ("isolation", "repeatable read", "isolation must be one of"),
    ],
)
def test_a_joining_call_with_an_invalid_explicit_value_is_refused_as_invalid(
    keyword: str, value: object, message: str
) -> None:
    # Validation precedes every active-transaction check, so what a joining
    # caller is told is that the value is malformed — never that it disagrees
    # with the active transaction, and never that the join is refused on any
    # other ground. The transaction survives because nothing entered its frame.
    port = ScriptedAdapter(Transact())
    db = account_db(port)

    def outer(_tx: Transaction) -> str:
        with pytest.raises(ValueError, match=message) as refusal:
            db.transact(_must_not_run, **cast("dict[str, Any]", {keyword: value}))
        assert not isinstance(refusal.value, TransactionOptionConflictError)
        return "survived"

    assert db.transact(outer) == "survived"
    assert port.calls == [BeginCall(), CommitCall()]


def test_the_retired_retries_keyword_is_refused() -> None:
    # `max_retries` replaced `retries` without an alias, so the old spelling is
    # an unknown keyword rather than a bound.
    port = ScriptedAdapter()
    with pytest.raises(TypeError, match="retries"):
        account_db(port).transact(_must_not_run, retries=3)  # pyright: ignore[reportCallIssue] - the retired keyword's refusal is what this proves
    assert port.calls == []


def test_rollback_only_refusal_keeps_the_original_retriability() -> None:
    # Spec §5: an inner deadlock dooms the transaction; even though the outer
    # callback catches it and returns normally, the commit refusal preserves the
    # cause's classification — the retry loop re-executes, and the fresh attempt
    # succeeds.
    port = ScriptedAdapter(Transact(Read(raises=deadlock())), Transact(Read(rows=[NEW_ROW])))
    db = account_db(port)

    def outer(_tx: Transaction) -> str:
        with contextlib.suppress(DatabaseError):
            db.transact(lambda inner_tx: inner_tx.find(mm.Account.where(mm.Account.id == 7)))
        return "caught"

    assert db.transact(outer) == "caught"
    assert port.calls.count(BeginCall()) == 2


# --------------------------------------------------------------------------- #
# Boundary outcomes (m-db-port / m-execution-lifecycle): which phase of the    #
# transaction failed decides what the caller sees and whether anything is      #
# re-executed, and only the composition root can reconcile the two.            #
# --------------------------------------------------------------------------- #
def _must_not_run_callback(_tx: Transaction) -> str:
    raise AssertionError("the callback runs only inside a transaction that began")


class _RollbackFailingPort(ScriptedAdapter):
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

    def transaction[T](
        self,
        body: Callable[[DatabaseConnection], T],
        *,
        isolation: IsolationLevel | None = None,
        on: DatabaseConnection | None = None,
    ) -> TransactionOutcome[T]:
        del isolation
        self.calls.append(BeginCall())
        outcome = body_outcome(on if on is not None else self, body)
        if isinstance(outcome, RolledBack):
            return RollbackFailed(outcome.trigger, self.rollback_error)
        self.calls.append(CommitCall())
        return outcome


def test_a_boundary_that_never_began_surfaces_its_error_after_one_attempt() -> None:
    # No callback ran, so there is nothing to re-execute — even though this
    # error would be retried on an attempt whose callback had run
    # (m-execution-lifecycle: a begin failure finishes the attempt `beginFailed`
    # and the invocation failed, without retry). The attempt had adopted before
    # it asked the boundary to begin, so the failure names that edition.
    never_began = deadlock()
    port = ScriptedAdapter(Transact(begin=never_began))
    serving = ServingModel(prepare_model(ACCOUNT, edition="adopted-before-begin"))
    with raises_contextualized(DatabaseError) as excinfo:
        Database.connect(port, serving, clock=FixedClock(FIXED)).transact(_must_not_run_callback)
    assert excinfo.value is never_began
    assert excinfo.edition == "adopted-before-begin"
    assert port.calls.count(BeginCall()) == 1
    # The private carrier that made it terminal is nowhere in what a caller
    # reads: it is neither the cause of the error the port made nor its context.
    assert excinfo.value.__cause__ is None
    assert excinfo.value.__context__ is None


def test_a_failed_rollback_reports_both_live_errors_and_is_never_retried() -> None:
    # Retriable on its own, and still terminal: what the transaction left behind
    # is unknown, so re-executing it could double the work it may have committed.
    triggering = deadlock()

    def failing(_tx: Transaction) -> str:
        raise triggering

    port = _RollbackFailingPort()
    with raises_contextualized(TransactionRollbackError) as excinfo:
        account_db(port).transact(failing)
    assert excinfo.value.triggering_error is triggering
    assert excinfo.value.rollback_error is port.rollback_error
    assert excinfo.value.__cause__ is port.rollback_error
    assert port.calls.count(BeginCall()) == 1


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


def test_a_control_flow_exception_inside_the_callback_surfaces_as_itself() -> None:
    # Contextualization is for ordinary failures: an interrupt leaving the
    # callback is never an `ExecutionFailure`, with or without a rollback
    # failure beside it, and the rollback still completes.
    interrupt = KeyboardInterrupt()

    def interrupted(_tx: Transaction) -> str:
        raise interrupt

    port = ScriptedAdapter(Transact())
    with pytest.raises(KeyboardInterrupt) as excinfo:
        account_db(port).transact(interrupted)
    assert excinfo.value is interrupt
    assert not isinstance(excinfo.value.__context__, ExecutionFailure)
    assert port.calls == [BeginCall(), RollbackCall()]


# --------------------------------------------------------------------------- #
# Adoption (spec §3): every outer attempt adopts the Serving Model's current    #
# selection before its boundary opens, a join inherits it, a retry adopts       #
# afresh, and a failure names the edition of the attempt that failed last.      #
# --------------------------------------------------------------------------- #
_A = prepare_model(ACCOUNT, edition="a")
_B = prepare_model(ACCOUNT, edition="b")


def _serving_db(port: DatabaseAdapter, serving: ServingModel) -> Database:
    return Database.connect(port, serving, clock=FixedClock(FIXED))


def test_a_static_connection_reports_one_edition_across_attempts_and_invocations() -> None:
    port = ScriptedAdapter(Transact(commit=deadlock()), Transact(), Transact())
    db = account_db(port)
    seen: list[str] = []

    def body(tx: Transaction) -> str:
        seen.append(tx.edition)
        return tx.edition

    first = db.transact(body)
    second = db.transact(body)
    assert first == second
    assert seen == [first] * 3
    assert first.startswith("static-")


def test_a_transaction_retains_the_selection_it_adopted_across_a_publication() -> None:
    serving = ServingModel(_A)
    port = ScriptedAdapter(Transact(), Transact())
    db = _serving_db(port, serving)

    def body(tx: Transaction) -> tuple[str, str]:
        before = tx.edition
        serving.publish(_B, expected=_A)
        return before, tx.edition

    assert db.transact(body) == ("a", "a")
    # The next invocation adopts what is serving by then.
    assert db.transact(lambda tx: tx.edition) == "b"


def test_a_join_inherits_the_outer_attempts_selection_without_adopting() -> None:
    serving = ServingModel(_A)
    port = ScriptedAdapter(Transact())
    db = _serving_db(port, serving)

    def outer(tx: Transaction) -> tuple[str, bool]:
        serving.publish(_B, expected=_A)
        # Serving already holds B, and the join still reports A on the very
        # same Transaction object: it adopted nothing.
        return db.transact(lambda inner: (inner.edition, inner is tx))

    assert db.transact(outer) == ("a", True)
    assert serving.current() is _B


def test_a_retry_adopts_the_selection_published_since_the_failed_attempt() -> None:
    serving = ServingModel(_A)
    port = ScriptedAdapter(Transact(commit=deadlock()), Transact())
    db = _serving_db(port, serving)
    seen: list[str] = []

    def body(tx: Transaction) -> str:
        seen.append(tx.edition)
        if len(seen) == 1:
            serving.publish(_B, expected=_A)
        return tx.edition

    assert db.transact(body) == "b"
    assert seen == ["a", "b"]
    assert port.calls.count(BeginCall()) == 2


def test_terminal_exhaustion_reports_the_final_attempts_edition() -> None:
    serving = ServingModel(_A)
    port = ScriptedAdapter(Transact(commit=deadlock()), Transact(commit=deadlock()))
    db = _serving_db(port, serving)

    def body(tx: Transaction) -> None:
        if tx.edition == "a":
            serving.publish(_B, expected=_A)

    with raises_contextualized(DatabaseError) as exhausted:
        db.transact(body, max_retries=1)
    assert exhausted.edition == "b"
    assert exhausted.value.is_retriable


def test_a_callback_failure_reports_the_edition_the_attempt_adopted() -> None:
    serving = ServingModel(_A)
    port = ScriptedAdapter(Transact())
    db = _serving_db(port, serving)

    def body(_tx: Transaction) -> None:
        raise RuntimeError("the callback's own")

    with raises_contextualized(RuntimeError, match="the callback's own") as failed:
        db.transact(body)
    assert failed.edition == "a"


def test_a_failed_rollback_keeps_both_errors_inside_the_contextualized_cause() -> None:
    triggering = deadlock()

    def failing(_tx: Transaction) -> str:
        raise triggering

    port = _RollbackFailingPort()
    with raises_contextualized(TransactionRollbackError) as failed:
        _serving_db(port, ServingModel(_A)).transact(failing)
    assert failed.edition == "a"
    assert failed.value.triggering_error is triggering
    assert failed.value.rollback_error is port.rollback_error


def test_two_databases_over_one_serving_model_flip_together() -> None:
    serving = ServingModel(_A)
    first = _serving_db(ScriptedAdapter(Transact(), Transact()), serving)
    second = _serving_db(ScriptedAdapter(Transact(), Transact()), serving)
    assert (first.transact(lambda tx: tx.edition), second.transact(lambda tx: tx.edition)) == (
        "a",
        "a",
    )
    serving.publish(_B, expected=_A)
    assert (first.transact(lambda tx: tx.edition), second.transact(lambda tx: tx.edition)) == (
        "b",
        "b",
    )


def test_the_deterministic_refusals_and_the_provider_opening_keep_their_own_types() -> None:
    # Everything `db.transact` refuses before adopting is raised as itself:
    # nothing has been adopted that a failure could be reported under.
    serving = ServingModel(_A)
    db = _serving_db(ScriptedAdapter(Transact()), serving)
    with pytest.raises(ValueError, match="max_retries must be >= 0"):
        db.transact(_must_not_run, max_retries=-1)
    with pytest.raises(ValueError, match="isolation must be one of"):
        db.transact(_must_not_run, isolation=cast("Any", "read uncommitted"))
    foreign = _serving_db(ScriptedAdapter(), serving)

    def outer(_tx: Transaction) -> str:
        with pytest.raises(TransactionOwnershipError):
            foreign.transact(_must_not_run)
        with pytest.raises(TransactionOptionConflictError):
            db.transact(_must_not_run, max_retries=3)
        return "survived"

    assert db.transact(outer) == "survived"


# --------------------------------------------------------------------------- #
# Optimistic-lock conflict opt-in (m-opt-lock "Retry contract";               #
# m-auto-retry): `retry_optimistic_conflicts` joins                           #
# `OptimisticLockConflictError` — and no other Write Effect Error — to the    #
# retriable set, the SAME `0`-then-`1` affected-rows transition               #
# `m-opt-lock-009` witnesses against real Postgres, reproduced here as one    #
# scripted attempt per affected-row count.                                    #
# --------------------------------------------------------------------------- #
def _observe_and_update(tx: Transaction) -> None:
    current = tx.find(mm.Account.where(mm.Account.id == 3)).result()
    tx.update(current.edit(balance=Decimal("20.00")))


def test_optimistic_conflict_surfaces_after_one_attempt_without_the_opt_in() -> None:
    port = ScriptedAdapter(
        Transact(
            Read(rows=[{"id": 3, "owner": "Grace", "balance": Decimal("10.00"), "version": 1}]),
            Write(affected=0),
        )
    )
    with raises_contextualized(OptimisticLockConflictError):
        account_db(port).transact(_observe_and_update, concurrency="optimistic")
    assert port.calls.count(BeginCall()) == 1


def test_optimistic_conflict_is_auto_retried_to_success_with_the_opt_in() -> None:
    grace = [{"id": 3, "owner": "Grace", "balance": Decimal("10.00"), "version": 1}]
    port = ScriptedAdapter(
        Transact(Read(rows=grace), Write(affected=0)), Transact(Read(rows=grace), Write())
    )
    account_db(port).transact(
        _observe_and_update, concurrency="optimistic", retry_optimistic_conflicts=True
    )
    assert (
        port.calls.count(BeginCall()) == 2
    )  # the conflicting attempt, then the retried (successful) attempt


def test_optimistic_conflict_opt_in_exhausts_its_bound() -> None:
    grace = [{"id": 3, "owner": "Grace", "balance": Decimal("10.00"), "version": 1}]
    port = ScriptedAdapter(
        *(
            Transact(Read(rows=grace), Write(affected=0)) for _ in range(3)
        )  # every attempt conflicts
    )
    with raises_contextualized(OptimisticLockConflictError) as excinfo:
        account_db(port).transact(
            _observe_and_update,
            concurrency="optimistic",
            max_retries=2,
            retry_optimistic_conflicts=True,
        )
    assert port.calls.count(BeginCall()) == 3
    assert "3 attempts (retries=2)" in "".join(excinfo.value.__notes__)


def test_optimistic_conflict_opt_in_is_inert_for_a_transient_failure() -> None:
    # The opt-in gates ONLY the conflict classification branch; a transient
    # database failure is retriable regardless of the flag's value (m-auto-retry
    # "Which failures are retriable" — transients are always retriable). This
    # RETRIABLE deadlock is classified retriable by `retriable_failure` alone
    # (the `or`'s left operand), so it never actually reaches the opt-in's own
    # predicate at all — see the NON-retriable sibling below for that.
    port = ScriptedAdapter(Transact(commit=deadlock()), Transact())
    assert account_db(port).transact(lambda _tx: "ok", retry_optimistic_conflicts=True) == "ok"
    assert port.calls.count(BeginCall()) == 2


def test_optimistic_conflict_opt_in_is_inert_for_a_non_retriable_database_error() -> None:
    # A NON-retriable `DatabaseError` (neither a direct
    # `OptimisticLockConflictError` nor a `RollbackOnlyError` wrapping one)
    # reaches the opt-in's own predicate (`_optimistic_conflict_retriable`,
    # since `retriable_failure` alone already calls it non-retriable) and
    # is classified non-retriable there too — the opt-in's structural
    # extension never widens the retriable set beyond the optimistic-lock
    # conflict shape itself.
    port = ScriptedAdapter(
        Transact(
            commit=DatabaseError(category="uniqueViolation", native_code="23505", message="dup")
        )
    )
    with raises_contextualized(DatabaseError):
        account_db(port).transact(lambda _tx: "ok", retry_optimistic_conflicts=True)
    assert port.calls.count(BeginCall()) == 1


def test_optimistic_conflict_opt_in_is_inert_in_locking_mode() -> None:
    # Locking mode never gates a versioned UPDATE (`m-opt-lock` "the version
    # column" — the shared read lock, not a version check, is what makes the
    # write correct), so there is nothing for the opt-in to ever retry: a
    # single-attempt commit, `retry_optimistic_conflicts` notwithstanding.
    port = ScriptedAdapter(
        Transact(
            Read(rows=[{"id": 3, "owner": "Grace", "balance": Decimal("10.00"), "version": 1}]),
            Write(),
        )
    )
    account_db(port).transact(
        _observe_and_update, concurrency="locking", retry_optimistic_conflicts=True
    )
    assert port.calls.count(BeginCall()) == 1


# Every sibling below scripts `[0, 1]` (or `[2, 1]`): a second attempt WOULD
# have succeeded, so `begins == 1` is evidence the opt-in refused to widen
# rather than an artifact of a persistently failing port.
def test_stale_write_is_never_retried_even_with_the_opt_in() -> None:
    # A locking-mode versioned UPDATE renders no gate, so its zero-row shortfall
    # is the stale write: the shared read lock should have made it impossible,
    # which makes it a consistency failure no re-read resolves.
    port = ScriptedAdapter(
        Transact(
            Read(rows=[{"id": 3, "owner": "Grace", "balance": Decimal("10.00"), "version": 1}]),
            Write(affected=0),
        )
    )
    with raises_contextualized(StaleWriteError):
        account_db(port).transact(
            _observe_and_update, concurrency="locking", retry_optimistic_conflicts=True
        )
    assert port.calls.count(BeginCall()) == 1


def _rename_person(tx: Transaction) -> None:
    fetched = tx.find(mm.Person.where(mm.Person.id == 1)).result()
    tx.update(fetched.edit(name="Grace"))


def test_missing_target_is_never_retried_even_with_the_opt_in() -> None:
    # An observation-free keyed write against an unversioned Entity: a shortfall
    # says only that the addressed rows are not there, and re-executing cannot
    # bring them into being. The renamed value comes from this transaction's own
    # read — an unversioned target needs no observation to WRITE, but every
    # keyed update needs a value some read of this store produced.
    port = ScriptedAdapter(Transact(Read(rows=[{"id": 1, "name": "Ada"}]), Write(affected=0)))
    with raises_contextualized(MissingTargetError):
        db_for(PERSON, port).transact(_rename_person, retry_optimistic_conflicts=True)
    assert port.calls.count(BeginCall()) == 1


def test_cardinality_corruption_is_never_retried_even_with_the_opt_in() -> None:
    # An EXCESS over the exact count means an accepted identity, storage, or
    # lowering invariant does not hold — an invariant failure rather than a
    # concurrency outcome, so the opt-in never widens to it either.
    port = ScriptedAdapter(
        Transact(
            Read(rows=[{"id": 3, "owner": "Grace", "balance": Decimal("10.00"), "version": 1}]),
            Write(affected=2),
        )
    )
    with raises_contextualized(CardinalityCorruptionError):
        account_db(port).transact(
            _observe_and_update, concurrency="optimistic", retry_optimistic_conflicts=True
        )
    assert port.calls.count(BeginCall()) == 1


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
    grace = [{"id": 3, "owner": "Grace", "balance": Decimal("10.00"), "version": 1}]
    port = ScriptedAdapter(
        Transact(Read(rows=grace), Write(affected=0)),
        Transact(Read(rows=grace), Write(), Read(rows=grace)),
    )
    db = account_db(port)

    def outer(_tx: Transaction) -> str:
        with contextlib.suppress(OptimisticLockConflictError):
            db.transact(_observe_update_then_force_flush)  # joins; conflicts mid-scope
        return "caught"

    assert db.transact(outer, concurrency="optimistic", retry_optimistic_conflicts=True) == "caught"
    assert (
        port.calls.count(BeginCall()) == 2
    )  # the conflicting attempt, then the retried (successful) attempt


# --------------------------------------------------------------------------- #
# Root defaults (spec §5): an outer invocation resolves each omitted keyword   #
# against the root's DatabaseOptions, an explicit keyword overrides it, a join  #
# inherits the invocation's resolved value, and `tx.options` is that record.    #
# --------------------------------------------------------------------------- #
_CONFIGURED = DatabaseOptions(
    max_retries=2, concurrency="locking", retry_optimistic_conflicts=True, isolation="serializable"
)


def _configured_db(port: DatabaseAdapter, options: DatabaseOptions = _CONFIGURED) -> Database:
    return Database.connect(port, ACCOUNT, options=options, clock=FixedClock(FIXED))


def test_an_unconfigured_root_resolves_the_built_in_record() -> None:
    port = ScriptedAdapter(Transact())
    assert account_db(port).transact(lambda tx: tx.options) == DatabaseOptions()


def test_omitted_keywords_resolve_to_the_roots_configured_defaults() -> None:
    port = ScriptedAdapter(Transact())
    db = _configured_db(port)
    assert db.transact(lambda tx: tx.options) is _CONFIGURED
    # Resolution reaches execution, not only inspection: the port is asked for
    # the root's level.
    assert port.calls == [BeginCall("serializable"), CommitCall()]


@pytest.mark.parametrize(
    ("keyword", "value"),
    [
        ("max_retries", 0),
        ("concurrency", "optimistic"),
        ("retry_optimistic_conflicts", False),
        ("isolation", "repeatable_read"),
    ],
)
def test_an_explicit_keyword_overrides_only_its_own_field(keyword: str, value: object) -> None:
    port = ScriptedAdapter(Transact())
    db = _configured_db(port)
    resolved = db.transact(lambda tx: tx.options, **cast("dict[str, Any]", {keyword: value}))
    assert resolved == DatabaseOptions(
        **cast("dict[str, Any]", {**_fields(_CONFIGURED), keyword: value})
    )
    assert resolved is not _CONFIGURED


def _fields(options: DatabaseOptions) -> dict[str, object]:
    return {
        "max_retries": options.max_retries,
        "concurrency": options.concurrency,
        "retry_optimistic_conflicts": options.retry_optimistic_conflicts,
        "isolation": options.isolation,
    }


def test_explicit_values_equal_to_the_defaults_reuse_the_roots_record() -> None:
    # An invocation that changes nothing allocates nothing: the root's own
    # record is what the transaction carries.
    port = ScriptedAdapter(Transact())
    db = _configured_db(port)
    resolved = db.transact(
        lambda tx: tx.options,
        max_retries=2,
        concurrency="locking",
        retry_optimistic_conflicts=True,
        isolation="serializable",
    )
    assert resolved is _CONFIGURED


def test_two_roots_resolve_independently() -> None:
    first = _configured_db(ScriptedAdapter(Transact()))
    second = account_db(ScriptedAdapter(Transact()))
    assert first.transact(lambda tx: tx.options) is _CONFIGURED
    assert second.transact(lambda tx: tx.options) == DatabaseOptions()


def test_every_retry_of_one_invocation_shares_one_resolved_record() -> None:
    port = ScriptedAdapter(Transact(commit=deadlock()), Transact(commit=deadlock()), Transact())
    seen: list[DatabaseOptions] = []

    def body(tx: Transaction) -> None:
        seen.append(tx.options)

    account_db(port).transact(body, isolation="repeatable_read", max_retries=5)
    assert len(seen) == 3
    assert all(options is seen[0] for options in seen)
    assert seen[0] == DatabaseOptions(max_retries=5, isolation="repeatable_read")
    assert port.calls.count(BeginCall("repeatable_read")) == 3


def test_a_join_reads_the_same_transaction_and_the_same_record() -> None:
    port = ScriptedAdapter(Transact())
    db = _configured_db(port)

    def outer(tx: Transaction) -> tuple[bool, bool]:
        return db.transact(lambda inner: (inner is tx, inner.options is tx.options))

    assert db.transact(outer) == (True, True)


@pytest.mark.parametrize(
    ("keyword", "equal", "different"),
    [
        ("max_retries", 0, 3),
        ("concurrency", "optimistic", "locking"),
        ("retry_optimistic_conflicts", False, True),
        ("isolation", "repeatable_read", "serializable"),
    ],
)
def test_a_join_inherits_an_outer_override_rather_than_the_roots_default(
    keyword: str, equal: object, different: object
) -> None:
    # The outer call overrides the root; a join omitting the field inherits the
    # OVERRIDE, repeating it is accepted, and naming the root's own value — or
    # any other — is a conflict, because the root never participates in a join
    # comparison on its own.
    port = ScriptedAdapter(Transact())
    db = _configured_db(port)
    root_value = _fields(_CONFIGURED)[keyword]

    def outer(tx: Transaction) -> str:
        assert db.transact(lambda inner: inner.options) is tx.options
        assert (
            db.transact(lambda inner: inner.options, **cast("dict[str, Any]", {keyword: equal}))
            is tx.options
        )
        with pytest.raises(TransactionOptionConflictError, match=keyword):
            db.transact(_must_not_run, **cast("dict[str, Any]", {keyword: root_value}))
        with pytest.raises(TransactionOptionConflictError, match=keyword):
            db.transact(_must_not_run, **cast("dict[str, Any]", {keyword: different}))
        return "survived"

    assert db.transact(outer, **cast("dict[str, Any]", {keyword: equal})) == "survived"
    level = "repeatable_read" if keyword == "isolation" else "serializable"
    assert port.calls == [BeginCall(cast("IsolationLevel", level)), CommitCall()]


def test_the_record_outlives_the_invocation_without_ambient_state() -> None:
    port = ScriptedAdapter(Transact())
    escaped: list[Transaction] = []
    _configured_db(port).transact(escaped.append)
    # No transaction is active any more, and the record is still the one the
    # invocation resolved — read off the transaction, not off any active state.
    assert escaped[0].options is _CONFIGURED


def test_the_roots_bound_admits_at_most_one_more_attempt_than_it_names() -> None:
    port = ScriptedAdapter(*(Transact(commit=deadlock()) for _ in range(3)))
    with raises_contextualized(DatabaseError):
        _configured_db(port).transact(lambda _tx: "ok")
    assert port.calls.count(BeginCall("serializable")) == 3


def test_a_zero_root_bound_means_one_attempt_and_an_explicit_bound_retries() -> None:
    zero = DatabaseOptions(max_retries=0)
    port = ScriptedAdapter(Transact(commit=deadlock()))
    with raises_contextualized(DatabaseError):
        _configured_db(port, zero).transact(lambda _tx: "ok")
    assert port.calls.count(BeginCall()) == 1
    port = ScriptedAdapter(Transact(commit=deadlock()), Transact())
    assert _configured_db(port, zero).transact(lambda _tx: "ok", max_retries=1) == "ok"
    assert port.calls.count(BeginCall()) == 2


def test_the_roots_conflict_opt_in_retries_an_eligible_conflict() -> None:
    grace = [{"id": 3, "owner": "Grace", "balance": Decimal("10.00"), "version": 1}]
    port = ScriptedAdapter(
        Transact(Read(rows=grace), Write(affected=0)), Transact(Read(rows=grace), Write())
    )
    opted_in = DatabaseOptions(retry_optimistic_conflicts=True)
    _configured_db(port, opted_in).transact(_observe_and_update)
    assert port.calls.count(BeginCall()) == 2


def test_an_explicit_false_disables_the_roots_conflict_opt_in_but_not_transient_retry() -> None:
    grace = [{"id": 3, "owner": "Grace", "balance": Decimal("10.00"), "version": 1}]
    opted_in = DatabaseOptions(retry_optimistic_conflicts=True)
    port = ScriptedAdapter(Transact(Read(rows=grace), Write(affected=0)))
    with raises_contextualized(OptimisticLockConflictError):
        _configured_db(port, opted_in).transact(
            _observe_and_update, retry_optimistic_conflicts=False
        )
    assert port.calls.count(BeginCall()) == 1
    port = ScriptedAdapter(Transact(commit=deadlock()), Transact())
    assert (
        _configured_db(port, opted_in).transact(lambda _tx: "ok", retry_optimistic_conflicts=False)
        == "ok"
    )
    assert port.calls.count(BeginCall()) == 2


def test_the_roots_locking_preference_drives_the_participating_reads_lock() -> None:
    # A root configured `locking` makes a participating read take the shared
    # lock without the call naming a preference; an explicit `optimistic` on a
    # versioned target takes none.
    row = {"id": 3, "owner": "Grace", "balance": Decimal("10.00"), "version": 1}
    locking = ScriptedAdapter(Transact(Read(rows=[row])))
    _configured_db(locking, DatabaseOptions(concurrency="locking")).transact(
        lambda tx: tx.find(mm.Account.where(mm.Account.id == 3)).result()
    )
    optimistic = ScriptedAdapter(Transact(Read(rows=[row])))
    _configured_db(optimistic, DatabaseOptions(concurrency="locking")).transact(
        lambda tx: tx.find(mm.Account.where(mm.Account.id == 3)).result(),
        concurrency="optimistic",
    )
    locked = [call.sql for call in locking.calls if isinstance(call, ReadCall)]
    unlocked = [call.sql for call in optimistic.calls if isinstance(call, ReadCall)]
    assert len(locked) == len(unlocked) == 1
    assert "for share" in locked[0]
    assert "for share" not in unlocked[0]
