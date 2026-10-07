"""The transaction runner (`execution.md`, Docker-free fake ports).

The observable behavior of `parallax.core.execution._runner`, driven through the
neutral Execution Scope a root's scope factory answers, with a transaction
factory that hands each callback the actual Attempt: commit and abort wiring,
join semantics (the same transaction, option conflicts, rollback-only
foreclosure), resolution of omitted options against the root's
`DatabaseOptions` and inspection of the resolved record, withheld values on
abort, escaped attempt references, the retry classification matrix, including
the requirement that a rollback-only commit refusal keeps its original cause's
retriability, and the adoption every attempt makes from the Serving Model:
which edition an attempt, a join, a retry, and a failure report, and what stays
on its own type because it happened before adoption.

Write-effect failures a Typed write verb's flush raises, and the retry
classification they reach, are the Snapshot transact suite's; everything else a
lifecycle Attempt does is its own suites'.
"""

from __future__ import annotations

import contextlib
from collections.abc import Callable
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Final, cast

import pytest

from parallax.conformance.scripted_clock import FixedClock
from parallax.core import Attr, DomainModel, Entity, Int32, attr, index, opt_lock
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
from parallax.core.execution import (
    DatabaseOptions,
    ExecutionFailure,
    ServingModel,
    TransactionAuthorityError,
    TransactionOptionConflictError,
    TransactionOwnershipError,
    TransactionRollbackError,
    prepare_model,
)
from parallax.core.execution._attempt import Attempt
from parallax.core.execution._planning import build_write_planner
from parallax.core.execution._scope import ExecutionScope
from parallax.core.object_query import ObjectQueryNode
from parallax.core.object_query._fluent import object_query_node
from parallax.core.unit_work import (
    DatabaseLoginActor,
    RollbackOnlyError,
    SubjectActor,
    TransactionSettings,
    UnitOfWork,
    UnitOfWorkError,
    WriteBatchReason,
    WritePlanner,
    run_unit_of_work,
)
from parallax.core.unit_work.uow import EscapedTransactionError
from parallax.core.write_plan import WritePlan
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
from tests._support.planner_probes import NO_ROW_READS, TEST_ACTOR_IDENTITY
from tests.unit.core.execution._execution_support import (
    ACCOUNT,
    FIXED,
    account_insert,
    itself,
    scope,
)
from tests.unit.core.execution._execution_support import root as owned_root

_NEW_ROW: Final = {"id": 7, "owner": "Newton", "balance": Decimal("5.00"), "version": 1}


def deadlock() -> DatabaseError:
    return DatabaseError(category="deadlock", native_code="40P01", message="deadlock detected")


def _account_seven() -> ObjectQueryNode:
    return object_query_node(mm.Account.where(mm.Account.id == 7))


def test_abort_discards_the_buffer_and_withholds_the_value() -> None:
    port = ScriptedAdapter(Transact())

    def fn(tx: Attempt) -> str:
        tx.uow.buffer(account_insert())
        raise RuntimeError("boom")

    with raises_contextualized(RuntimeError, match="boom"):
        scope(port).transact(fn, itself)
    # Nothing flushed: the buffered write never reached the port.
    assert port.calls == [BeginCall(), RollbackCall()]


def test_an_escaped_transaction_reference_raises_after_the_scope_ends() -> None:
    port = ScriptedAdapter(Transact())
    escaped: list[Attempt] = []

    def fn(tx: Attempt) -> None:
        escaped.append(tx)

    scope(port).transact(fn, itself)
    with pytest.raises(EscapedTransactionError):
        escaped[0].uow.buffer(account_insert())


# --------------------------------------------------------------------------- #
# Join semantics: same Attempt, option conflicts, foreclosure.             #
# --------------------------------------------------------------------------- #
def test_join_receives_the_same_transaction_and_returns_immediately() -> None:
    port = ScriptedAdapter(Transact())
    db = scope(port)

    def outer(tx: Attempt) -> int:
        inner = db.transact(lambda inner_tx: (inner_tx is tx, 42), itself)
        assert inner == (True, 42)
        return inner[1]

    assert db.transact(outer, itself) == 42
    assert port.calls.count(BeginCall()) == 1  # the join opened no second database transaction


def test_join_with_equal_or_omitted_options_inherits() -> None:
    port = ScriptedAdapter(Transact())
    db = scope(port)

    def outer(_tx: Attempt) -> str:
        # Explicit-and-equal to the resolved defaults: accepted, not a conflict.
        return db.transact(
            lambda _inner: "joined",
            itself,
            max_retries=10,
            concurrency="optimistic",
            retry_optimistic_conflicts=False,
            isolation="read_committed",
        )

    assert db.transact(outer, itself) == "joined"


def _must_not_run(_tx: Attempt) -> None:  # pragma: no cover - conflict forecloses it
    raise AssertionError("the joined closure must not run on an option conflict")


@dataclass(frozen=True, slots=True)
class _Authorization:
    name: str


@dataclass(frozen=True, slots=True)
class _Principal:
    subject: str
    database_authorization: _Authorization


def test_independently_captured_equal_principal_authority_joins_by_value() -> None:
    port = ScriptedAdapter(Transact())
    root = owned_root(port)
    first = root.using_principal(_Principal("alice", _Authorization("role-a")))
    second = root.using_principal(_Principal("alice", _Authorization("role-a")))

    def outer(tx: Attempt) -> tuple[bool, str]:
        return second.transact(lambda joined: (joined is tx, "joined"), itself)

    assert first.transact(outer, itself) == (True, "joined")
    assert port.calls == [BeginCall(), CommitCall()]


@pytest.mark.parametrize(
    "joining",
    [
        _Principal("bob", _Authorization("role-a")),
        _Principal("alice", _Authorization("role-b")),
        None,
    ],
)
def test_authority_mismatch_refuses_before_the_joining_body_and_leaves_outer_usable(
    joining: _Principal | None,
) -> None:
    port = ScriptedAdapter(Transact())
    root = owned_root(port)
    owner = root.using_principal(_Principal("alice", _Authorization("role-a")))
    other = root.using_database_login() if joining is None else root.using_principal(joining)
    ran: list[bool] = []

    def outer(_tx: Attempt) -> str:
        with pytest.raises(TransactionAuthorityError) as refused:
            other.transact(lambda _joined: ran.append(True), itself)
        assert refused.value.code == "transaction-authority-mismatch"
        return "survived"

    assert owner.transact(outer, itself) == "survived"
    assert ran == []
    assert port.calls == [BeginCall(), CommitCall()]


def test_root_aliases_share_ownership_while_unrelated_roots_do_not() -> None:
    port = ScriptedAdapter(Transact())
    root = owned_root(port)
    alias = root.with_options(max_retries=3)
    owner = root.using_database_login()
    joining_alias = alias.using_database_login()
    foreign_root = owned_root(ScriptedAdapter())
    foreign = foreign_root.using_database_login()

    def outer(tx: Attempt) -> str:
        assert joining_alias.transact(lambda joined: joined is tx, itself)
        with pytest.raises(TransactionOwnershipError):
            foreign.transact(_must_not_run, itself)
        return "survived"

    assert owner.transact(outer, itself) == "survived"


def test_join_refusal_precedence_is_ownership_then_rollback_authority_then_options() -> None:
    port = ScriptedAdapter(Transact())
    root = owned_root(port)
    owner = root.using_principal(_Principal("alice", _Authorization("role-a")))
    mismatched = root.using_principal(_Principal("bob", _Authorization("role-b")))
    foreign_root = owned_root(ScriptedAdapter())
    foreign = foreign_root.using_database_login()

    def outer(_tx: Attempt) -> str:
        with pytest.raises(TransactionAuthorityError):
            mismatched.transact(_must_not_run, itself, max_retries=3)
        with pytest.raises(RuntimeError, match="inner failure"):
            owner.transact(_raise_inner, itself)
        with pytest.raises(TransactionOwnershipError):
            foreign.transact(_must_not_run, itself, max_retries=3)
        with pytest.raises(RollbackOnlyError) as rollback_only:
            mismatched.transact(_must_not_run, itself, max_retries=3)
        assert isinstance(rollback_only.value.__cause__, RuntimeError)
        return "withheld"

    with raises_contextualized(RollbackOnlyError) as refused_commit:
        owner.transact(outer, itself)
    assert isinstance(refused_commit.value.__cause__, RuntimeError)
    assert port.calls == [BeginCall(), RollbackCall()]


@pytest.mark.parametrize(
    ("mode", "actor_type", "value"),
    [
        ("principal", SubjectActor, "alice"),
        ("login", DatabaseLoginActor, "test-login"),
    ],
)
def test_write_planning_receives_the_original_captured_actor(
    mode: str,
    actor_type: type[SubjectActor] | type[DatabaseLoginActor],
    value: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: list[SubjectActor | DatabaseLoginActor] = []
    finalize = WritePlanner.finalize

    def recording(self: WritePlanner, request: Any) -> Any:
        seen.append(request.actor_identity)
        return finalize(self, request)

    monkeypatch.setattr(WritePlanner, "finalize", recording)
    port = ScriptedAdapter(Transact(Write()))
    root = owned_root(port)
    scoped = (
        root.using_principal(_Principal("alice", _Authorization("role-a")))
        if mode == "principal"
        else root.using_database_login()
    )
    captured_actor = cast("Any", scoped)._capture.actor

    scoped.transact(lambda tx: tx.uow.buffer(account_insert()), itself)

    assert seen == [captured_actor]
    assert isinstance(seen[0], actor_type)
    assert seen[0].value == value


_CONFLICTING_JOINS: list[tuple[str, Callable[[ExecutionScope], object]]] = [
    ("max_retries", lambda db: db.transact(_must_not_run, itself, max_retries=3)),
    ("concurrency", lambda db: db.transact(_must_not_run, itself, concurrency="locking")),
    (
        "retry_optimistic_conflicts",
        lambda db: db.transact(_must_not_run, itself, retry_optimistic_conflicts=True),
    ),
    # The transaction these join resolved the root's Read Committed, so NAMING
    # a different level conflicts on the same terms as the other three.
    ("isolation", lambda db: db.transact(_must_not_run, itself, isolation="serializable")),
]


@pytest.mark.parametrize(("option", "join"), _CONFLICTING_JOINS)
def test_join_with_a_conflicting_explicit_option_raises(
    option: str, join: Callable[[ExecutionScope], object]
) -> None:
    port = ScriptedAdapter(Transact())
    db = scope(port)

    def outer(_tx: Attempt) -> str:
        with pytest.raises(TransactionOptionConflictError, match=option):
            join(db)
        return "survived"

    # The conflict is refused before the joined closure runs, and refusing it
    # does not doom the outer transaction (nothing entered the joined frame).
    assert db.transact(outer, itself) == "survived"


# --------------------------------------------------------------------------- #
# Isolation: a closed vocabulary, refused here and mapped by the adapter.      #
# --------------------------------------------------------------------------- #
def test_an_omitted_isolation_asks_the_port_for_the_roots_read_committed() -> None:
    # Omission resolves to the root's default, and an unconfigured root's is a
    # concrete Read Committed: the port is asked for that level rather than for
    # nothing, so a database configured with a stronger default still opens
    # this boundary at the level Parallax resolved.
    port = ScriptedAdapter(Transact())
    scope(port).transact(lambda _tx: "ok", itself)
    assert port.calls == [BeginCall("read_committed"), CommitCall()]


@pytest.mark.parametrize("level", sorted(ISOLATION_LEVELS))
def test_every_level_of_the_vocabulary_reaches_the_port(level: str) -> None:
    # Every member of the closed vocabulary crosses the seam, and crosses it as
    # itself: the runner refuses what is outside the vocabulary and interprets
    # nothing inside it, leaving the mapping to the adapter that owns an engine.
    port = ScriptedAdapter(Transact())
    scope(port).transact(lambda _tx: "ok", itself, isolation=cast("IsolationLevel", level))
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
        scope(port).transact(_must_not_run, itself, isolation=cast("Any", level))
    assert port.calls == []


def test_a_joined_call_naming_a_level_outside_the_vocabulary_is_refused_as_invalid() -> None:
    # The refusal precedes the join comparison, so what a caller is told is that
    # the level does not exist — never that it disagrees with the active
    # boundary, which would read as though spelling it correctly would have been
    # accepted when the same level was already active.
    port = ScriptedAdapter(Transact())
    db = scope(port)

    def outer(_tx: Attempt) -> str:
        with pytest.raises(ValueError, match="isolation must be one of") as refusal:
            db.transact(_must_not_run, itself, isolation=cast("Any", "repeatable read"))
        assert not isinstance(refusal.value, TransactionOptionConflictError)
        return "survived"

    assert db.transact(outer, itself, isolation="repeatable_read") == "survived"
    assert port.calls == [BeginCall("repeatable_read"), CommitCall()]


def test_every_retry_of_one_invocation_opens_at_the_requested_isolation() -> None:
    # The level belongs to the invocation rather than to one physical attempt:
    # a re-executed callback that silently ran at the database's default would
    # answer differently from the attempt before it.
    port = ScriptedAdapter(Transact(commit=deadlock()), Transact(commit=deadlock()), Transact())
    assert scope(port).transact(lambda _tx: "ok", itself, isolation="serializable") == "ok"
    assert port.calls.count(BeginCall("serializable")) == 3


def test_a_join_omitting_or_repeating_the_active_isolation_is_accepted() -> None:
    port = ScriptedAdapter(Transact())
    db = scope(port)

    def outer(_tx: Attempt) -> str:
        assert db.transact(lambda _inner: "omitted", itself) == "omitted"
        return db.transact(lambda _inner: "repeated", itself, isolation="serializable")

    assert db.transact(outer, itself, isolation="serializable") == "repeated"
    # Two joins, and neither opened a second boundary to re-negotiate.
    assert port.calls == [BeginCall("serializable"), CommitCall()]


def test_a_join_naming_a_different_isolation_raises_before_its_callback_runs() -> None:
    port = ScriptedAdapter(Transact())
    db = scope(port)

    def outer(_tx: Attempt) -> str:
        with pytest.raises(TransactionOptionConflictError, match="isolation"):
            db.transact(_must_not_run, itself, isolation="repeatable_read")
        return "survived"

    assert db.transact(outer, itself, isolation="serializable") == "survived"


def test_joining_a_doomed_transaction_is_foreclosed_before_its_closure_runs() -> None:
    port = ScriptedAdapter(Transact())
    db = scope(port)
    ran: list[bool] = []

    def outer(_tx: Attempt) -> str:
        with pytest.raises(RuntimeError, match="inner failure"):
            db.transact(_raise_inner, itself)
        with pytest.raises(RollbackOnlyError):
            db.transact(lambda _inner: ran.append(True), itself)
        return "unreachable value"

    # The outer callback caught everything and returned normally, but the inner
    # failure doomed the transaction: commit is refused and the value withheld.
    with raises_contextualized(RollbackOnlyError) as excinfo:
        db.transact(outer, itself)
    assert isinstance(excinfo.value.__cause__, RuntimeError)
    assert ran == []
    assert port.calls == [BeginCall(), RollbackCall()]


def _raise_inner(_tx: Attempt) -> None:
    raise RuntimeError("inner failure")


def test_a_non_transactional_find_opens_no_unit_of_work_to_participate_in() -> None:
    # A standalone read is outside demarcation entirely: no `begin`, no `commit`,
    # and so no unit of work whose participation its values could carry. That is
    # the demarcation fact behind the read executor's own rule — a read with no
    # unit of work behind it stamps no participation and files into no index,
    # while the values it publishes still retain the state each row observed
    # (`test_transaction_reads.py` pins that half).
    port = ScriptedAdapter(Read(rows=[_NEW_ROW]))
    assert scope(port).read_rows(_account_seven()).rows == (_NEW_ROW,)
    assert [type(op) for op in port.calls] == [ReadCall]


def test_bare_unit_of_work_on_the_thread_is_refused() -> None:
    port = ScriptedAdapter()
    db = scope(port)

    def executor(  # pragma: no cover - never flushed
        _plan: WritePlan, *, trigger: WriteBatchReason, bind_deferred: object, completed: object
    ) -> None:
        raise AssertionError("no flush expected")

    def body(_uow: UnitOfWork) -> None:
        with pytest.raises(UnitOfWorkError, match="bare unit of work"):
            db.transact(lambda _tx: None, itself)

    model = model_of(ACCOUNT)
    run_unit_of_work(
        body,
        settings=TransactionSettings(),
        clock=FixedClock(FIXED),
        meta=model,
        flush_executor=executor,
        acquire_rows=NO_ROW_READS,
        planner=build_write_planner(model),
        actor_identity=TEST_ACTOR_IDENTITY,
        evidence_policy_for=opt_lock.view(model).required_key,
    )


# --------------------------------------------------------------------------- #
# Resource-root ownership (ADR 0007): scopes from one root or its aliases join, #
# while scopes from an unrelated root do not. Settled before the later guards. #
# --------------------------------------------------------------------------- #
def test_an_alias_of_the_owner_joins_and_receives_the_identical_transaction() -> None:
    port = ScriptedAdapter(Transact())
    db = scope(port)
    alias = db  # a second name for one object — the only thing that ever joins

    def outer(tx: Attempt) -> int:
        assert alias.transact(lambda inner_tx: (inner_tx is tx, 42), itself) == (True, 42)
        return 42

    assert db.transact(outer, itself) == 42
    assert port.calls.count(BeginCall()) == 1


def test_a_different_database_over_the_same_model_and_adapter_is_refused() -> None:
    port = ScriptedAdapter(Transact())
    owner = scope(port)
    foreign = scope(port)  # same model, same adapter, same clock; a different object

    def outer(_tx: Attempt) -> str:
        with pytest.raises(TransactionOwnershipError) as excinfo:
            foreign.transact(_must_not_run, itself)
        assert excinfo.value.code == "transaction-owner-mismatch"
        # Neither scope is retained: the refusal names no root at all.
        assert repr(owner) not in str(excinfo.value)
        assert repr(foreign) not in str(excinfo.value)
        return "survived"

    # Refusing the join opened no second database transaction and did not doom
    # the outer one — nothing entered the joined frame.
    assert owner.transact(outer, itself) == "survived"
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
    owner = scope(port)
    foreign = scope(port, _equal_account_model())
    # The two accepted models are equal entity for entity, and that buys nothing.
    assert list(model_of(ACCOUNT).entities) == list(model_of(_equal_account_model()).entities)

    def outer(_tx: Attempt) -> str:
        with pytest.raises(TransactionOwnershipError):
            foreign.transact(_must_not_run, itself)
        return "survived"

    assert owner.transact(outer, itself) == "survived"


def test_the_ownership_refusal_reaches_no_adapter() -> None:
    port = ScriptedAdapter(Transact())
    owner = scope(port)
    foreign = scope(port)

    def outer(_tx: Attempt) -> str:
        # The boundary's script holds no statement, so returning at all is the
        # proof that the refusal performed none.
        with pytest.raises(TransactionOwnershipError):
            foreign.transact(_must_not_run, itself)
        return "survived"

    assert owner.transact(outer, itself) == "survived"


def test_ownership_is_settled_before_rollback_only_before_option_conflicts() -> None:
    port = ScriptedAdapter(Transact())
    owner = scope(port)
    foreign = scope(port)

    def outer(_tx: Attempt) -> str:
        # Doom the boundary, so rollback-only joining would refuse ANY join.
        with pytest.raises(RuntimeError, match="inner failure"):
            owner.transact(_raise_inner, itself)
        # A foreign scope carrying a conflicting option: the doomed boundary
        # and the option conflict would each raise, and neither is the answer.
        with pytest.raises(TransactionOwnershipError):
            foreign.transact(_must_not_run, itself, max_retries=3)
        # Nothing beyond the outer boundary's own `begin` ever reached the port.
        assert port.calls == [BeginCall()]
        # Through the owner, rollback-only foreclosure answers before the
        # otherwise-conflicting option is compared.
        with pytest.raises(RollbackOnlyError):
            owner.transact(_must_not_run, itself, max_retries=3)
        return "unreachable value"

    with raises_contextualized(RollbackOnlyError):
        owner.transact(outer, itself)
    assert port.calls == [BeginCall(), RollbackCall()]


# --------------------------------------------------------------------------- #
# Bounded retry (m-auto-retry through db.transact).                            #
# --------------------------------------------------------------------------- #
def test_a_deadlock_is_retried_and_the_reexecution_succeeds() -> None:
    port = ScriptedAdapter(Transact(commit=deadlock()), Transact(commit=deadlock()), Transact())
    assert scope(port).transact(lambda _tx: "ok", itself) == "ok"
    assert port.calls.count(BeginCall()) == 3


def test_exhaustion_reraises_the_failure_with_the_attempt_count() -> None:
    port = ScriptedAdapter(*(Transact(commit=deadlock()) for _ in range(3)))
    with raises_contextualized(DatabaseError) as excinfo:
        scope(port).transact(lambda _tx: "ok", itself, max_retries=2)
    assert port.calls.count(BeginCall()) == 3
    assert excinfo.value.is_retriable  # the surfaced error is the failure itself
    # The core loop's own note spells the bound by its own parameter name; the
    # public keyword that supplied the number is `max_retries`.
    assert "3 attempts (retries=2)" in "".join(excinfo.value.__notes__)


def test_the_default_bound_is_ten_reexecutions() -> None:
    port = ScriptedAdapter(*(Transact(commit=deadlock()) for _ in range(11)))
    with raises_contextualized(DatabaseError) as excinfo:
        scope(port).transact(lambda _tx: "ok", itself)
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
        scope(port).transact(lambda _tx: "ok", itself)
    assert port.calls.count(BeginCall()) == 1


def test_retries_zero_disables_the_loop() -> None:
    port = ScriptedAdapter(Transact(commit=deadlock()))
    with raises_contextualized(DatabaseError):
        scope(port).transact(lambda _tx: "ok", itself, max_retries=0)
    assert port.calls.count(BeginCall()) == 1


def test_negative_retries_are_rejected_before_any_attempt() -> None:
    port = ScriptedAdapter()
    with pytest.raises(ValueError, match="max_retries must be >= 0"):
        scope(port).transact(lambda _tx: "ok", itself, max_retries=-1)
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
        scope(port).transact(_must_not_run, itself, **cast("dict[str, Any]", {keyword: value}))
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
    db = scope(port)

    def outer(_tx: Attempt) -> str:
        with pytest.raises(ValueError, match=message) as refusal:
            db.transact(_must_not_run, itself, **cast("dict[str, Any]", {keyword: value}))
        assert not isinstance(refusal.value, TransactionOptionConflictError)
        return "survived"

    assert db.transact(outer, itself) == "survived"
    assert port.calls == [BeginCall(), CommitCall()]


def test_the_retired_retries_keyword_is_refused() -> None:
    # `max_retries` replaced `retries` without an alias, so the old spelling is
    # an unknown keyword rather than a bound.
    port = ScriptedAdapter()
    with pytest.raises(TypeError, match="retries"):
        scope(port).transact(_must_not_run, itself, retries=3)  # pyright: ignore[reportCallIssue] - the retired keyword's refusal is what this proves
    assert port.calls == []


def test_rollback_only_refusal_keeps_the_original_retriability() -> None:
    # An inner deadlock dooms the transaction; even though the outer
    # callback catches it and returns normally, the commit refusal preserves the
    # cause's classification — the retry loop re-executes, and the fresh attempt
    # succeeds.
    port = ScriptedAdapter(Transact(Read(raises=deadlock())), Transact(Read(rows=[_NEW_ROW])))
    db = scope(port)

    def outer(_tx: Attempt) -> str:
        with contextlib.suppress(DatabaseError):
            db.transact(lambda inner_tx: inner_tx.read_rows(_account_seven()), itself)
        return "caught"

    assert db.transact(outer, itself) == "caught"
    assert port.calls.count(BeginCall()) == 2


# --------------------------------------------------------------------------- #
# Boundary outcomes (m-db-port / m-execution-lifecycle): which phase of the    #
# transaction failed decides what the caller sees and whether anything is      #
# re-executed, and only the composition root can reconcile the two.            #
# --------------------------------------------------------------------------- #
def _must_not_run_callback(_tx: Attempt) -> str:
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
        scope(port, serving).transact(_must_not_run_callback, itself)
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

    def failing(_tx: Attempt) -> str:
        raise triggering

    port = _RollbackFailingPort()
    with raises_contextualized(TransactionRollbackError) as excinfo:
        scope(port).transact(failing, itself)
    assert excinfo.value.triggering_error is triggering
    assert excinfo.value.rollback_error is port.rollback_error
    assert excinfo.value.__cause__ is port.rollback_error
    assert port.calls.count(BeginCall()) == 1


def test_a_failed_rollback_leaves_a_control_flow_trigger_primary() -> None:
    # An interrupt or a cancellation is not downgraded to an ordinary error: it
    # stays what the caller receives, carrying the rollback failure as its cause.
    interrupt = KeyboardInterrupt()

    def interrupted(_tx: Attempt) -> str:
        raise interrupt

    port = _RollbackFailingPort()
    with pytest.raises(KeyboardInterrupt) as excinfo:
        scope(port).transact(interrupted, itself)
    assert excinfo.value is interrupt
    assert excinfo.value.__cause__ is port.rollback_error


def test_a_control_flow_exception_inside_the_callback_surfaces_as_itself() -> None:
    # Contextualization is for ordinary failures: an interrupt leaving the
    # callback is never an `ExecutionFailure`, with or without a rollback
    # failure beside it, and the rollback still completes.
    interrupt = KeyboardInterrupt()

    def interrupted(_tx: Attempt) -> str:
        raise interrupt

    port = ScriptedAdapter(Transact())
    with pytest.raises(KeyboardInterrupt) as excinfo:
        scope(port).transact(interrupted, itself)
    assert excinfo.value is interrupt
    assert not isinstance(excinfo.value.__context__, ExecutionFailure)
    assert port.calls == [BeginCall(), RollbackCall()]


# --------------------------------------------------------------------------- #
# Adoption: every outer attempt adopts the Serving Model's current              #
# selection before its boundary opens, a join inherits it, a retry adopts       #
# afresh, and a failure names the edition of the attempt that failed last.      #
# --------------------------------------------------------------------------- #
_A = prepare_model(ACCOUNT, edition="a")
_B = prepare_model(ACCOUNT, edition="b")


def test_an_unpublished_serving_model_reports_one_edition_across_attempts_and_invocations() -> None:
    port = ScriptedAdapter(Transact(commit=deadlock()), Transact(), Transact())
    db = scope(port)
    seen: list[str] = []

    def body(tx: Attempt) -> str:
        seen.append(tx.edition)
        return tx.edition

    first = db.transact(body, itself)
    second = db.transact(body, itself)
    assert first == second == "test"
    assert seen == [first] * 3


def test_a_transaction_retains_the_selection_it_adopted_across_a_publication() -> None:
    serving = ServingModel(_A)
    port = ScriptedAdapter(Transact(), Transact())
    db = scope(port, serving)

    def body(tx: Attempt) -> tuple[str, str]:
        before = tx.edition
        serving.publish(_B, expected=_A)
        return before, tx.edition

    assert db.transact(body, itself) == ("a", "a")
    # The next invocation adopts what is serving by then.
    assert db.transact(lambda tx: tx.edition, itself) == "b"


def test_a_join_inherits_the_outer_attempts_selection_without_adopting() -> None:
    serving = ServingModel(_A)
    port = ScriptedAdapter(Transact())
    db = scope(port, serving)

    def outer(tx: Attempt) -> tuple[str, bool]:
        serving.publish(_B, expected=_A)
        # Serving already holds B, and the join still reports A on the very
        # same Attempt object: it adopted nothing.
        return db.transact(lambda inner: (inner.edition, inner is tx), itself)

    assert db.transact(outer, itself) == ("a", True)
    assert serving.current() is _B


def test_a_retry_adopts_the_selection_published_since_the_failed_attempt() -> None:
    serving = ServingModel(_A)
    port = ScriptedAdapter(Transact(commit=deadlock()), Transact())
    db = scope(port, serving)
    seen: list[str] = []

    def body(tx: Attempt) -> str:
        seen.append(tx.edition)
        if len(seen) == 1:
            serving.publish(_B, expected=_A)
        return tx.edition

    assert db.transact(body, itself) == "b"
    assert seen == ["a", "b"]
    assert port.calls.count(BeginCall()) == 2


def test_terminal_exhaustion_reports_the_final_attempts_edition() -> None:
    serving = ServingModel(_A)
    port = ScriptedAdapter(Transact(commit=deadlock()), Transact(commit=deadlock()))
    db = scope(port, serving)

    def body(tx: Attempt) -> None:
        if tx.edition == "a":
            serving.publish(_B, expected=_A)

    with raises_contextualized(DatabaseError) as exhausted:
        db.transact(body, itself, max_retries=1)
    assert exhausted.edition == "b"
    assert exhausted.value.is_retriable


def test_a_callback_failure_reports_the_edition_the_attempt_adopted() -> None:
    serving = ServingModel(_A)
    port = ScriptedAdapter(Transact())
    db = scope(port, serving)

    def body(_tx: Attempt) -> None:
        raise RuntimeError("the callback's own")

    with raises_contextualized(RuntimeError, match="the callback's own") as failed:
        db.transact(body, itself)
    assert failed.edition == "a"


def test_a_failed_rollback_keeps_both_errors_inside_the_contextualized_cause() -> None:
    triggering = deadlock()

    def failing(_tx: Attempt) -> str:
        raise triggering

    port = _RollbackFailingPort()
    with raises_contextualized(TransactionRollbackError) as failed:
        scope(port, ServingModel(_A)).transact(failing, itself)
    assert failed.edition == "a"
    assert failed.value.triggering_error is triggering
    assert failed.value.rollback_error is port.rollback_error


def test_two_databases_over_one_serving_model_flip_together() -> None:
    serving = ServingModel(_A)
    first = scope(ScriptedAdapter(Transact(), Transact()), serving)
    second = scope(ScriptedAdapter(Transact(), Transact()), serving)
    assert (
        first.transact(lambda tx: tx.edition, itself),
        second.transact(lambda tx: tx.edition, itself),
    ) == (
        "a",
        "a",
    )
    serving.publish(_B, expected=_A)
    assert (
        first.transact(lambda tx: tx.edition, itself),
        second.transact(lambda tx: tx.edition, itself),
    ) == (
        "b",
        "b",
    )


def test_the_deterministic_refusals_and_the_provider_opening_keep_their_own_types() -> None:
    # Everything `db.transact` refuses before adopting is raised as itself:
    # nothing has been adopted that a failure could be reported under.
    serving = ServingModel(_A)
    db = scope(ScriptedAdapter(Transact()), serving)
    with pytest.raises(ValueError, match="max_retries must be >= 0"):
        db.transact(_must_not_run, itself, max_retries=-1)
    with pytest.raises(ValueError, match="isolation must be one of"):
        db.transact(_must_not_run, itself, isolation=cast("Any", "read uncommitted"))
    foreign = scope(ScriptedAdapter(), serving)

    def outer(_tx: Attempt) -> str:
        with pytest.raises(TransactionOwnershipError):
            foreign.transact(_must_not_run, itself)
        with pytest.raises(TransactionOptionConflictError):
            db.transact(_must_not_run, itself, max_retries=3)
        return "survived"

    assert db.transact(outer, itself) == "survived"


# --------------------------------------------------------------------------- #
# Optimistic-lock conflict opt-in (m-opt-lock "Retry contract";               #
# m-auto-retry): `retry_optimistic_conflicts` joins                           #
# `OptimisticLockConflictError` — and no other Write Effect Error — to the    #
# retriable set, the SAME `0`-then-`1` affected-rows transition               #
# `m-opt-lock-009` witnesses against real Postgres, reproduced here as one    #
# scripted attempt per affected-row count.                                    #
# --------------------------------------------------------------------------- #


def test_optimistic_conflict_opt_in_is_inert_for_a_transient_failure() -> None:
    # The opt-in gates ONLY the conflict classification branch; a transient
    # database failure is retriable regardless of the flag's value (m-auto-retry
    # "Which failures are retriable" — transients are always retriable). This
    # RETRIABLE deadlock is classified retriable by `retriable_failure` alone
    # (the `or`'s left operand), so it never actually reaches the opt-in's own
    # predicate at all — see the NON-retriable sibling below for that.
    port = ScriptedAdapter(Transact(commit=deadlock()), Transact())
    assert scope(port).transact(lambda _tx: "ok", itself, retry_optimistic_conflicts=True) == "ok"
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
        scope(port).transact(lambda _tx: "ok", itself, retry_optimistic_conflicts=True)
    assert port.calls.count(BeginCall()) == 1


# --------------------------------------------------------------------------- #
# Root defaults: an outer invocation resolves each omitted keyword              #
# against the root's DatabaseOptions, an explicit keyword overrides it, a join  #
# inherits the invocation's resolved value, and `tx.options` is that record.    #
# --------------------------------------------------------------------------- #
_CONFIGURED = DatabaseOptions(
    max_retries=2, concurrency="locking", retry_optimistic_conflicts=True, isolation="serializable"
)


def _configured_db(
    port: DatabaseAdapter[Any], options: DatabaseOptions = _CONFIGURED
) -> ExecutionScope:
    return scope(port, options=options)


def test_an_unconfigured_root_resolves_the_built_in_record() -> None:
    port = ScriptedAdapter(Transact())
    assert scope(port).transact(lambda tx: tx.options, itself) == DatabaseOptions()


def test_omitted_keywords_resolve_to_the_roots_configured_defaults() -> None:
    port = ScriptedAdapter(Transact())
    db = _configured_db(port)
    assert db.transact(lambda tx: tx.options, itself) is _CONFIGURED
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
    resolved = db.transact(
        lambda tx: tx.options, itself, **cast("dict[str, Any]", {keyword: value})
    )
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
        itself,
        max_retries=2,
        concurrency="locking",
        retry_optimistic_conflicts=True,
        isolation="serializable",
    )
    assert resolved is _CONFIGURED


def test_two_roots_resolve_independently() -> None:
    first = _configured_db(ScriptedAdapter(Transact()))
    second = scope(ScriptedAdapter(Transact()))
    assert first.transact(lambda tx: tx.options, itself) is _CONFIGURED
    assert second.transact(lambda tx: tx.options, itself) == DatabaseOptions()


def test_every_retry_of_one_invocation_shares_one_resolved_record() -> None:
    port = ScriptedAdapter(Transact(commit=deadlock()), Transact(commit=deadlock()), Transact())
    seen: list[DatabaseOptions] = []

    def body(tx: Attempt) -> None:
        seen.append(tx.options)

    scope(port).transact(body, itself, isolation="repeatable_read", max_retries=5)
    assert len(seen) == 3
    assert all(options is seen[0] for options in seen)
    assert seen[0] == DatabaseOptions(max_retries=5, isolation="repeatable_read")
    assert port.calls.count(BeginCall("repeatable_read")) == 3


def test_a_join_reads_the_same_transaction_and_the_same_record() -> None:
    port = ScriptedAdapter(Transact())
    db = _configured_db(port)

    def outer(tx: Attempt) -> tuple[bool, bool]:
        return db.transact(lambda inner: (inner is tx, inner.options is tx.options), itself)

    assert db.transact(outer, itself) == (True, True)


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

    def outer(tx: Attempt) -> str:
        assert db.transact(lambda inner: inner.options, itself) is tx.options
        assert (
            db.transact(
                lambda inner: inner.options, itself, **cast("dict[str, Any]", {keyword: equal})
            )
            is tx.options
        )
        with pytest.raises(TransactionOptionConflictError, match=keyword):
            db.transact(_must_not_run, itself, **cast("dict[str, Any]", {keyword: root_value}))
        with pytest.raises(TransactionOptionConflictError, match=keyword):
            db.transact(_must_not_run, itself, **cast("dict[str, Any]", {keyword: different}))
        return "survived"

    assert db.transact(outer, itself, **cast("dict[str, Any]", {keyword: equal})) == "survived"
    level = "repeatable_read" if keyword == "isolation" else "serializable"
    assert port.calls == [BeginCall(cast("IsolationLevel", level)), CommitCall()]


def test_the_record_outlives_the_invocation_without_ambient_state() -> None:
    port = ScriptedAdapter(Transact())
    escaped: list[Attempt] = []
    _configured_db(port).transact(escaped.append, itself)
    # No transaction is active any more, and the record is still the one the
    # invocation resolved — read off the transaction, not off any active state.
    assert escaped[0].options is _CONFIGURED


def test_the_roots_bound_admits_at_most_one_more_attempt_than_it_names() -> None:
    port = ScriptedAdapter(*(Transact(commit=deadlock()) for _ in range(3)))
    with raises_contextualized(DatabaseError):
        _configured_db(port).transact(lambda _tx: "ok", itself)
    assert port.calls.count(BeginCall("serializable")) == 3


def test_a_zero_root_bound_means_one_attempt_and_an_explicit_bound_retries() -> None:
    zero = DatabaseOptions(max_retries=0)
    port = ScriptedAdapter(Transact(commit=deadlock()))
    with raises_contextualized(DatabaseError):
        _configured_db(port, zero).transact(lambda _tx: "ok", itself)
    assert port.calls.count(BeginCall()) == 1
    port = ScriptedAdapter(Transact(commit=deadlock()), Transact())
    assert _configured_db(port, zero).transact(lambda _tx: "ok", itself, max_retries=1) == "ok"
    assert port.calls.count(BeginCall()) == 2
