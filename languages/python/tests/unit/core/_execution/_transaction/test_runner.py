"""The transaction runner (`execution.md`, Docker-free fake ports).

The observable behavior of `parallax.core._execution._transaction._runner`, driven through the
neutral Execution Scope a root's scope factory answers, with a context
factory that hands each callback the actual attempt — writable or read-only:
commit and abort wiring, the access mode each entrypoint requests, join
semantics (the same attempt, the admission order, cross-mode and option
refusals, rollback-only foreclosure), resolution of omitted options against
the root's `TxnOptions` and inspection of the resolved record, withheld
values on abort, escaped attempt references, the retry classification matrix, including
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
import random
from collections.abc import Callable
from dataclasses import dataclass
from decimal import Decimal
from types import TracebackType
from typing import Any, Final, cast

import pytest

from parallax.conformance._lifecycle_recording import RecordingLifecycleProvider
from parallax.core import Attr, DomainModel, Entity, Int32, attr, auto_retry, index
from parallax.core._execution._scope import ExecutionScope
from parallax.core._execution._transaction._attempt import ReadOnlyTxnAttempt, TxnAttempt
from parallax.core._execution._unit_work.uow import EscapedTransactionError
from parallax.core.auto_retry import RetryCandidate
from parallax.core.db_error import DatabaseError
from parallax.core.db_port import (
    ISOLATION_LEVELS,
    AccessMode,
    ConnectionContext,
    DatabaseAdapter,
    DatabaseConnection,
    IsolationLevel,
    RollbackFailed,
    RolledBack,
    TransactionOutcome,
)
from parallax.core.entity._authored_resolver import object_query_node
from parallax.core.entity._model import model_of
from parallax.core.execution import (
    ExecutionFailure,
    ReadOnlyTxnOptions,
    ServingModel,
    TransactionAccessModeError,
    TransactionAuthorityError,
    TransactionOptionConflictError,
    TransactionOwnershipError,
    TransactionRollbackError,
    TxnOptions,
    prepare_model,
)
from parallax.core.execution_lifecycle import AttemptRolledBack, TransactionAttemptFinished
from parallax.core.metamodel import AttributeIdentity, EntityIdentity
from parallax.core.object_query import ObjectQueryNode
from parallax.core.unit_work import (
    DatabaseLoginActor,
    OptimisticLockConflictError,
    RollbackOnlyError,
    SubjectActor,
    WritePlanner,
)
from parallax.core.write_plan.steps import KeyTarget
from tests._support import mirrored_models as mm
from tests._support.adoption import raises_contextualized
from tests._support.db_port import (
    BeginCall,
    CommitCall,
    Read,
    ReadCall,
    RollbackCall,
    ScriptedAdapter,
    ScriptedContext,
    ScriptedRuntime,
    Transact,
    Write,
    body_outcome,
)
from tests.unit.core._execution._execution_support import (
    ACCOUNT,
    account_insert,
    itself,
    scope,
)
from tests.unit.core._execution._execution_support import root as owned_root

_NEW_ROW: Final = {"id": 7, "owner": "Newton", "balance": Decimal("5.00"), "version": 1}


def deadlock() -> DatabaseError:
    return DatabaseError(category="deadlock", native_code="40P01", message="deadlock detected")


def _account_seven() -> ObjectQueryNode:
    return object_query_node(mm.Account.where(mm.Account.id == 7), ACCOUNT)


def test_abort_discards_the_buffer_and_withholds_the_value() -> None:
    port = ScriptedAdapter(Transact())

    def fn(tx: TxnAttempt) -> str:
        tx.uow.buffer(account_insert())
        raise RuntimeError("boom")

    with raises_contextualized(RuntimeError, match="boom"):
        scope(port).transact(fn, itself)
    # Nothing flushed: the buffered write never reached the port.
    assert port.calls == [BeginCall(), RollbackCall()]


def test_an_escaped_transaction_reference_raises_after_the_scope_ends() -> None:
    port = ScriptedAdapter(Transact())
    escaped: list[TxnAttempt] = []

    def fn(tx: TxnAttempt) -> None:
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

    def outer(tx: TxnAttempt) -> int:
        inner = db.transact(lambda inner_tx: (inner_tx is tx, 42), itself)
        assert inner == (True, 42)
        return inner[1]

    assert db.transact(outer, itself) == 42
    assert port.calls.count(BeginCall()) == 1  # the join opened no second database transaction


def test_join_with_equal_or_omitted_options_inherits() -> None:
    port = ScriptedAdapter(Transact())
    db = scope(port)

    def outer(_tx: TxnAttempt) -> str:
        # Explicit-and-equal to the resolved defaults: accepted, not a conflict.
        return db.transact(
            lambda _inner: "joined",
            itself,
            max_retries=10,
            concurrency="optimistic",
            isolation="read_committed",
        )

    assert db.transact(outer, itself) == "joined"


def _must_not_run(_tx: object) -> None:  # pragma: no cover - a refusal forecloses it
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

    def outer(tx: TxnAttempt) -> tuple[bool, str]:
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

    def outer(_tx: TxnAttempt) -> str:
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

    def outer(tx: TxnAttempt) -> str:
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

    def outer(_tx: TxnAttempt) -> str:
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
    # The transaction these join resolved the root's Read Committed, so NAMING
    # a different level conflicts on the same terms as the other two.
    ("isolation", lambda db: db.transact(_must_not_run, itself, isolation="serializable")),
]


@pytest.mark.parametrize(("option", "join"), _CONFLICTING_JOINS)
def test_join_with_a_conflicting_explicit_option_raises(
    option: str, join: Callable[[ExecutionScope], object]
) -> None:
    port = ScriptedAdapter(Transact())
    db = scope(port)

    def outer(_tx: TxnAttempt) -> str:
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

    def outer(_tx: TxnAttempt) -> str:
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

    def outer(_tx: TxnAttempt) -> str:
        assert db.transact(lambda _inner: "omitted", itself) == "omitted"
        return db.transact(lambda _inner: "repeated", itself, isolation="serializable")

    assert db.transact(outer, itself, isolation="serializable") == "repeated"
    # Two joins, and neither opened a second boundary to re-negotiate.
    assert port.calls == [BeginCall("serializable"), CommitCall()]


def test_a_join_naming_a_different_isolation_raises_before_its_callback_runs() -> None:
    port = ScriptedAdapter(Transact())
    db = scope(port)

    def outer(_tx: TxnAttempt) -> str:
        with pytest.raises(TransactionOptionConflictError, match="isolation"):
            db.transact(_must_not_run, itself, isolation="repeatable_read")
        return "survived"

    assert db.transact(outer, itself, isolation="serializable") == "survived"


def test_joining_a_doomed_transaction_is_foreclosed_before_its_closure_runs() -> None:
    port = ScriptedAdapter(Transact())
    db = scope(port)
    ran: list[bool] = []

    def outer(_tx: TxnAttempt) -> str:
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


def _raise_inner(_tx: object) -> None:
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


# --------------------------------------------------------------------------- #
# Resource-root ownership (ADR 0007): scopes from one root or its aliases join, #
# while scopes from an unrelated root do not. Settled before the later guards. #
# --------------------------------------------------------------------------- #
def test_an_alias_of_the_owner_joins_and_receives_the_identical_transaction() -> None:
    port = ScriptedAdapter(Transact())
    db = scope(port)
    alias = db  # a second name for one object — the only thing that ever joins

    def outer(tx: TxnAttempt) -> int:
        assert alias.transact(lambda inner_tx: (inner_tx is tx, 42), itself) == (True, 42)
        return 42

    assert db.transact(outer, itself) == 42
    assert port.calls.count(BeginCall()) == 1


def test_a_different_database_over_the_same_model_and_adapter_is_refused() -> None:
    port = ScriptedAdapter(Transact())
    owner = scope(port)
    foreign = scope(port)  # same model, same adapter, same clock; a different object

    def outer(_tx: TxnAttempt) -> str:
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

    def outer(_tx: TxnAttempt) -> str:
        with pytest.raises(TransactionOwnershipError):
            foreign.transact(_must_not_run, itself)
        return "survived"

    assert owner.transact(outer, itself) == "survived"


def test_the_ownership_refusal_reaches_no_adapter() -> None:
    port = ScriptedAdapter(Transact())
    owner = scope(port)
    foreign = scope(port)

    def outer(_tx: TxnAttempt) -> str:
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

    def outer(_tx: TxnAttempt) -> str:
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

    def outer(_tx: TxnAttempt) -> str:
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

    def outer(_tx: TxnAttempt) -> str:
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
def _must_not_run_callback(_tx: TxnAttempt) -> str:
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
        access_mode: AccessMode | None = None,
        on: DatabaseConnection | None = None,
    ) -> TransactionOutcome[T]:
        del isolation, access_mode
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

    def failing(_tx: TxnAttempt) -> str:
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

    def interrupted(_tx: TxnAttempt) -> str:
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

    def interrupted(_tx: TxnAttempt) -> str:
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

    def body(tx: TxnAttempt) -> str:
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

    def body(tx: TxnAttempt) -> tuple[str, str]:
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

    def outer(tx: TxnAttempt) -> tuple[str, bool]:
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

    def body(tx: TxnAttempt) -> str:
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

    def body(tx: TxnAttempt) -> None:
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

    def body(_tx: TxnAttempt) -> None:
        raise RuntimeError("the callback's own")

    with raises_contextualized(RuntimeError, match="the callback's own") as failed:
        db.transact(body, itself)
    assert failed.edition == "a"


def test_a_failed_rollback_keeps_both_errors_inside_the_contextualized_cause() -> None:
    triggering = deadlock()

    def failing(_tx: TxnAttempt) -> str:
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

    def outer(_tx: TxnAttempt) -> str:
        with pytest.raises(TransactionOwnershipError):
            foreign.transact(_must_not_run, itself)
        with pytest.raises(TransactionOptionConflictError):
            db.transact(_must_not_run, itself, max_retries=3)
        return "survived"

    assert db.transact(outer, itself) == "survived"


# --------------------------------------------------------------------------- #
# Recoverable-conflict replay (m-auto-retry; m-opt-lock "Retry contract"): an  #
# internal optimistic conflict replays like a transient database failure, the  #
# caller sees the failure the attempt raised with its own chain, and anything  #
# a later cleanup step raises ends the invocation instead.                     #
# --------------------------------------------------------------------------- #
_ROW_2: Final = EntityIdentity("parallax.compatibility", "Account")
_KEY_2: Final = KeyTarget(key_attributes=(AttributeIdentity(_ROW_2, "id"),), key_values=((2,),))


def _conflict() -> OptimisticLockConflictError:
    return OptimisticLockConflictError(_ROW_2, _KEY_2, 1, 0)


def test_an_optimistic_conflict_is_replayed_without_any_option() -> None:
    port = ScriptedAdapter(Transact(), Transact())
    attempts: list[TxnAttempt] = []

    def body(tx: TxnAttempt) -> str:
        attempts.append(tx)
        if len(attempts) == 1:
            raise _conflict()
        return "ok"

    assert scope(port).transact(body, itself) == "ok"
    assert port.calls == [BeginCall(), RollbackCall(), BeginCall(), CommitCall()]
    assert attempts[0] is not attempts[1]


def test_a_conflict_a_caught_join_left_behind_is_replayed_through_the_rollback_only_refusal() -> (
    None
):
    port = ScriptedAdapter(Transact(), Transact())
    db = scope(port)
    attempts: list[int] = []

    def inner(_tx: TxnAttempt) -> None:
        raise _conflict()

    def outer(_tx: TxnAttempt) -> str:
        attempts.append(len(attempts))
        if len(attempts) == 1:
            with contextlib.suppress(OptimisticLockConflictError):
                db.transact(inner, itself)
        return "caught"

    assert db.transact(outer, itself) == "caught"
    assert port.calls.count(BeginCall()) == 2


def test_an_exhausted_conflict_surfaces_as_the_identical_failure_with_its_own_chain() -> None:
    port = ScriptedAdapter(Transact(), Transact())
    raised: list[OptimisticLockConflictError] = []
    origin = RuntimeError("what the callback was handling")

    def body(_tx: TxnAttempt) -> None:
        conflict = _conflict()
        raised.append(conflict)
        try:
            raise origin
        except RuntimeError:
            raise conflict from None

    with raises_contextualized(OptimisticLockConflictError) as excinfo:
        scope(port).transact(body, itself, max_retries=1)
    assert excinfo.value is raised[-1]
    assert excinfo.value.__cause__ is None
    assert excinfo.value.__suppress_context__
    assert excinfo.value.__context__ is origin
    assert "2 attempts (retries=1)" in "".join(excinfo.value.__notes__)
    assert not any(isinstance(link, RetryCandidate) for link in _chain(excinfo.value))


def test_a_non_retriable_database_error_is_not_replayed() -> None:
    port = ScriptedAdapter(
        Transact(
            commit=DatabaseError(category="uniqueViolation", native_code="23505", message="dup")
        )
    )
    with raises_contextualized(DatabaseError):
        scope(port).transact(lambda _tx: "ok", itself)
    assert port.calls.count(BeginCall()) == 1


class _ReleaseObservingAdapter(ScriptedAdapter):
    """A scripted adapter whose connections record what each release was told
    ended the attempt, and whose ``interrupted`` release raises instead."""

    def __init__(self, *script: Transact, interrupted: int | None = None) -> None:
        super().__init__(*script)
        self.released_after: list[BaseException | None] = []
        self.interrupt = KeyboardInterrupt()
        self.interrupted = interrupted

    def open(self) -> ScriptedRuntime:
        adapter = self

        class _Runtime(ScriptedRuntime):
            def new_bound_context(self, authorization: object | None) -> ConnectionContext:
                del authorization
                return _ObservedContext(self, adapter)

        return _Runtime(self)


class _ObservedContext(ScriptedContext):
    def __init__(self, runtime: ScriptedRuntime, adapter: _ReleaseObservingAdapter) -> None:
        super().__init__(runtime)
        self._adapter = adapter

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
        /,
    ) -> None:
        super().__exit__(exc_type, exc, traceback)
        adapter = self._adapter
        adapter.released_after.append(exc)
        if len(adapter.released_after) == adapter.interrupted:
            raise adapter.interrupt


def test_the_release_after_an_eligible_failure_is_told_the_failure_itself() -> None:
    port = _ReleaseObservingAdapter(Transact(commit=deadlock()), Transact())
    assert scope(port).transact(lambda _tx: "ok", itself) == "ok"
    first, second = port.released_after
    assert isinstance(first, DatabaseError)
    assert first.is_retriable
    assert second is None


def test_a_release_that_fails_after_an_eligible_failure_ends_the_invocation() -> None:
    port = _ReleaseObservingAdapter(Transact(commit=deadlock()), Transact(), interrupted=1)
    with pytest.raises(KeyboardInterrupt) as excinfo:
        scope(port).transact(lambda _tx: "ok", itself)
    assert excinfo.value is port.interrupt
    assert port.calls.count(BeginCall()) == 1
    (released_after,) = port.released_after
    assert excinfo.value.__context__ is released_after
    assert not any(isinstance(link, RetryCandidate) for link in _chain(excinfo.value))


class _AtTheCeiling(random.Random):
    """Draws every delay at the top of its range."""

    def uniform(self, a: float, b: float) -> float:
        del a
        return b


@dataclass(frozen=True, slots=True)
class _Wait:
    """What had happened when the loop slept: the delay, the lifecycle
    transitions delivered so far, and the connections already released."""

    seconds: float
    transitions: tuple[str, ...]
    released: int


def _waits_recorded(
    monkeypatch: pytest.MonkeyPatch, recorder: RecordingLifecycleProvider, port: ScriptedAdapter
) -> list[_Wait]:
    """Substitute the loop's sleep, recording each wait against ``recorder``'s
    one root and ``port``'s releases, and draw every delay at its ceiling."""
    waits: list[_Wait] = []

    def sleep(seconds: float) -> None:
        (root,) = recorder.roots
        transitions = tuple(type(event).__name__ for event in root.events)
        waits.append(_Wait(seconds, transitions, len(port.cleanups)))

    monkeypatch.setattr(auto_retry, "_sleep", sleep)
    monkeypatch.setattr(auto_retry, "_rng", _AtTheCeiling(0))
    return waits


def _committing(_attempts: list[int]) -> Callable[[TxnAttempt], str]:
    return lambda _tx: "ok"


def _conflicting_once(attempts: list[int]) -> Callable[[TxnAttempt], str]:
    def body(_tx: TxnAttempt) -> str:
        attempts.append(len(attempts))
        if len(attempts) == 1:
            raise _conflict()
        return "ok"

    return body


@pytest.mark.parametrize(
    ("script", "body"),
    [
        ((Transact(commit=deadlock()), Transact()), _committing),
        ((Transact(), Transact()), _conflicting_once),
    ],
    ids=["deadlock-at-commit", "conflict-in-the-callback"],
)
def test_a_replay_waits_only_after_the_failed_attempt_released_and_finished(
    monkeypatch: pytest.MonkeyPatch,
    script: tuple[Transact, ...],
    body: Callable[[list[int]], Callable[[TxnAttempt], str]],
) -> None:
    recorder = RecordingLifecycleProvider()
    port = ScriptedAdapter(*script)
    waits = _waits_recorded(monkeypatch, recorder, port)

    assert scope(port, provider=recorder).transact(body([]), itself) == "ok"

    (wait,) = waits
    assert wait.seconds == auto_retry._delay(1, _AtTheCeiling(0))  # pyright: ignore[reportPrivateUsage] - the first attempt's ceiling
    assert wait.released == 1
    assert wait.transitions[-3:] == (
        "ReleaseStarted",
        "ReleaseFinished",
        "TransactionAttemptFinished",
    )
    (root,) = recorder.roots
    after = [type(event).__name__ for event in root.events[len(wait.transitions) :]]
    assert after[0] == "TransactionAttemptStarted"
    finished = root.events[len(wait.transitions) - 1]
    assert isinstance(finished, TransactionAttemptFinished)
    assert isinstance(finished.outcome, AttemptRolledBack)
    assert finished.outcome.failure.retry_eligible


def test_nothing_that_ends_the_invocation_waits(monkeypatch: pytest.MonkeyPatch) -> None:
    recorder = RecordingLifecycleProvider()
    port = ScriptedAdapter(
        Transact(begin=deadlock()),
        Transact(commit=DatabaseError(category="uniqueViolation", native_code="23505", message="")),
        Transact(commit=deadlock()),
    )
    waits = _waits_recorded(monkeypatch, recorder, port)
    db = scope(port)
    with raises_contextualized(DatabaseError):
        db.transact(_must_not_run_callback, itself)
    with raises_contextualized(DatabaseError):
        db.transact(lambda _tx: "ok", itself)
    with raises_contextualized(DatabaseError):
        db.transact(lambda _tx: "ok", itself, max_retries=0)
    assert waits == []


def _chain(failure: BaseException) -> list[BaseException]:
    links: list[BaseException] = []
    link: BaseException | None = failure
    while link is not None:
        links.append(link)
        link = link.__cause__ or link.__context__
    return links


# --------------------------------------------------------------------------- #
# Root defaults: an outer invocation resolves each omitted keyword              #
# against the root's TxnOptions, an explicit keyword overrides it, a join  #
# inherits the invocation's resolved value, and `tx.options` is that record.    #
# --------------------------------------------------------------------------- #
_CONFIGURED = TxnOptions(max_retries=2, concurrency="locking", isolation="serializable")


def _configured_db(port: DatabaseAdapter[Any], options: TxnOptions = _CONFIGURED) -> ExecutionScope:
    return scope(port, options=options)


def test_an_unconfigured_root_resolves_the_built_in_record() -> None:
    port = ScriptedAdapter(Transact())
    assert scope(port).transact(lambda tx: tx.options, itself) == TxnOptions()


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
        ("isolation", "repeatable_read"),
    ],
)
def test_an_explicit_keyword_overrides_only_its_own_field(keyword: str, value: object) -> None:
    port = ScriptedAdapter(Transact())
    db = _configured_db(port)
    resolved = db.transact(
        lambda tx: tx.options, itself, **cast("dict[str, Any]", {keyword: value})
    )
    assert resolved == TxnOptions(
        **cast("dict[str, Any]", {**_fields(_CONFIGURED), keyword: value})
    )
    assert resolved is not _CONFIGURED


def _fields(options: TxnOptions) -> dict[str, object]:
    return {
        "max_retries": options.max_retries,
        "concurrency": options.concurrency,
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
        isolation="serializable",
    )
    assert resolved is _CONFIGURED


def test_two_roots_resolve_independently() -> None:
    first = _configured_db(ScriptedAdapter(Transact()))
    second = scope(ScriptedAdapter(Transact()))
    assert first.transact(lambda tx: tx.options, itself) is _CONFIGURED
    assert second.transact(lambda tx: tx.options, itself) == TxnOptions()


def test_every_retry_of_one_invocation_shares_one_resolved_record() -> None:
    port = ScriptedAdapter(Transact(commit=deadlock()), Transact(commit=deadlock()), Transact())
    seen: list[TxnOptions] = []

    def body(tx: TxnAttempt) -> None:
        seen.append(tx.options)

    scope(port).transact(body, itself, isolation="repeatable_read", max_retries=5)
    assert len(seen) == 3
    assert all(options is seen[0] for options in seen)
    assert seen[0] == TxnOptions(max_retries=5, isolation="repeatable_read")
    assert port.calls.count(BeginCall("repeatable_read")) == 3


def test_a_join_reads_the_same_transaction_and_the_same_record() -> None:
    port = ScriptedAdapter(Transact())
    db = _configured_db(port)

    def outer(tx: TxnAttempt) -> tuple[bool, bool]:
        return db.transact(lambda inner: (inner is tx, inner.options is tx.options), itself)

    assert db.transact(outer, itself) == (True, True)


@pytest.mark.parametrize(
    ("keyword", "equal", "different"),
    [
        ("max_retries", 0, 3),
        ("concurrency", "optimistic", "locking"),
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

    def outer(tx: TxnAttempt) -> str:
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
    escaped: list[TxnAttempt] = []
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
    zero = TxnOptions(max_retries=0)
    port = ScriptedAdapter(Transact(commit=deadlock()))
    with raises_contextualized(DatabaseError):
        _configured_db(port, zero).transact(lambda _tx: "ok", itself)
    assert port.calls.count(BeginCall()) == 1
    port = ScriptedAdapter(Transact(commit=deadlock()), Transact())
    assert _configured_db(port, zero).transact(lambda _tx: "ok", itself, max_retries=1) == "ok"
    assert port.calls.count(BeginCall()) == 2


# --------------------------------------------------------------------------- #
# Read-only invocations: the same path with a read-only attempt.              #
# --------------------------------------------------------------------------- #
def test_each_entrypoint_asks_the_port_for_its_own_access_mode_on_every_attempt() -> None:
    port = ScriptedAdapter(Transact(commit=deadlock()), Transact(), Transact())
    db = scope(port)
    assert db.read_only(lambda _rtx: "read", itself) == "read"
    assert db.transact(lambda _tx: "written", itself) == "written"
    assert port.calls == [
        BeginCall("read_committed", "read_only"),
        RollbackCall(),
        BeginCall("read_committed", "read_only"),
        CommitCall(),
        BeginCall("read_committed", "read_write"),
        CommitCall(),
    ]


def test_a_read_only_attempt_owns_no_unit_of_work() -> None:
    port = ScriptedAdapter(Transact())
    attempts: list[ReadOnlyTxnAttempt] = []
    scope(port).read_only(attempts.append, itself)
    (attempt,) = attempts
    assert isinstance(attempt, ReadOnlyTxnAttempt)
    assert not hasattr(attempt, "uow")


def test_a_read_only_read_takes_no_lock_even_under_a_locking_root() -> None:
    port = ScriptedAdapter(Transact(Read(rows=[_NEW_ROW])))
    db = scope(port, options=TxnOptions(concurrency="locking"))
    result = db.read_only(lambda rtx: rtx.read_rows(_account_seven()), itself)
    assert result.rows == (_NEW_ROW,)
    (read,) = [call for call in port.calls if isinstance(call, ReadCall)]
    assert "for share" not in read.sql


def test_read_only_options_resolve_the_bound_and_level_alone() -> None:
    port = ScriptedAdapter(Transact(), Transact())
    db = scope(
        port, options=TxnOptions(max_retries=2, concurrency="locking", isolation="serializable")
    )
    inherited = db.read_only(lambda rtx: rtx.options, itself)
    overridden = db.read_only(lambda rtx: rtx.options, itself, isolation="repeatable_read")
    assert inherited == ReadOnlyTxnOptions(max_retries=2, isolation="serializable")
    assert overridden == ReadOnlyTxnOptions(max_retries=2, isolation="repeatable_read")
    assert not hasattr(inherited, "concurrency")
    assert port.calls[0] == BeginCall("serializable", "read_only")


@pytest.mark.parametrize(
    ("keyword", "value", "message"),
    [
        ("max_retries", -1, "max_retries must be >= 0"),
        ("max_retries", True, "max_retries must be a nonnegative int"),
        ("isolation", "repeatable read", "isolation must be one of"),
        ("isolation", None, "isolation must be one of"),
    ],
)
def test_a_read_only_value_outside_its_fields_contract_is_refused_before_the_port(
    keyword: str, value: object, message: str
) -> None:
    port = ScriptedAdapter()
    with pytest.raises(ValueError, match=message):
        scope(port).read_only(_must_not_run, itself, **{keyword: value})  # pyright: ignore[reportArgumentType]
    assert port.calls == []


def test_a_read_only_join_receives_the_same_attempt_and_inherits_its_options() -> None:
    port = ScriptedAdapter(Transact())
    db = scope(port)

    def outer(rtx: ReadOnlyTxnAttempt) -> tuple[bool, bool]:
        omitted = db.read_only(lambda joined: joined is rtx, itself)
        repeated = db.read_only(
            lambda joined: joined is rtx, itself, max_retries=10, isolation="read_committed"
        )
        return omitted, repeated

    assert db.read_only(outer, itself) == (True, True)
    assert port.calls == [BeginCall("read_committed", "read_only"), CommitCall()]


_CONFLICTING_READ_ONLY_JOINS: list[tuple[str, Callable[[ExecutionScope], object]]] = [
    ("max_retries", lambda db: db.read_only(_must_not_run, itself, max_retries=3)),
    ("isolation", lambda db: db.read_only(_must_not_run, itself, isolation="serializable")),
]


@pytest.mark.parametrize(("option", "join"), _CONFLICTING_READ_ONLY_JOINS)
def test_a_read_only_join_naming_a_conflicting_option_is_refused(
    option: str, join: Callable[[ExecutionScope], object]
) -> None:
    port = ScriptedAdapter(Transact())
    db = scope(port)

    def outer(_rtx: ReadOnlyTxnAttempt) -> str:
        with pytest.raises(TransactionOptionConflictError, match=option):
            join(db)
        return "survived"

    assert db.read_only(outer, itself) == "survived"


def test_a_writable_join_into_a_read_only_transaction_is_refused_before_its_callback() -> None:
    port = ScriptedAdapter(Transact())
    db = scope(port)

    def outer(_rtx: ReadOnlyTxnAttempt) -> str:
        with pytest.raises(TransactionAccessModeError) as refused:
            db.transact(_must_not_run, itself)
        assert refused.value.code == "transaction-access-mode-mismatch"
        assert "writable invocation cannot join the active read-only" in str(refused.value)
        return "survived"

    # A refusal before admission dooms nothing: the outer attempt still commits.
    assert db.read_only(outer, itself) == "survived"
    assert port.calls == [BeginCall("read_committed", "read_only"), CommitCall()]


def test_a_read_only_join_into_a_writable_transaction_is_refused_before_its_callback() -> None:
    port = ScriptedAdapter(Transact())
    db = scope(port)

    def outer(_tx: TxnAttempt) -> str:
        with pytest.raises(TransactionAccessModeError) as refused:
            db.read_only(_must_not_run, itself)
        assert "read-only invocation cannot join the active writable" in str(refused.value)
        return "survived"

    assert db.transact(outer, itself) == "survived"
    assert port.calls == [BeginCall(), CommitCall()]


def test_join_admission_runs_ownership_rollback_only_authority_access_mode_then_options() -> None:
    port = ScriptedAdapter(Transact())
    root = owned_root(port)
    owner = root.using_principal(_Principal("alice", _Authorization("role-a")))
    mismatched = root.using_principal(_Principal("bob", _Authorization("role-b")))
    foreign = owned_root(ScriptedAdapter()).using_database_login()

    def outer(_rtx: ReadOnlyTxnAttempt) -> str:
        # Authority outranks the access mode, and the access mode an option.
        with pytest.raises(TransactionAuthorityError):
            mismatched.transact(_must_not_run, itself, max_retries=3)
        with pytest.raises(TransactionAccessModeError):
            owner.transact(_must_not_run, itself, max_retries=3)
        with pytest.raises(RuntimeError, match="inner failure"):
            owner.read_only(_raise_inner, itself)
        # Ownership outranks rollback-only, which outranks everything after it.
        with pytest.raises(TransactionOwnershipError):
            foreign.transact(_must_not_run, itself)
        with pytest.raises(RollbackOnlyError):
            mismatched.transact(_must_not_run, itself, max_retries=3)
        return "withheld"

    with raises_contextualized(RollbackOnlyError) as refused_commit:
        owner.read_only(outer, itself)
    assert isinstance(refused_commit.value.__cause__, RuntimeError)
    assert port.calls == [BeginCall("read_committed", "read_only"), RollbackCall()]


def test_a_failed_read_only_join_dooms_the_attempt_even_when_the_outer_callback_catches_it() -> (
    None
):
    port = ScriptedAdapter(Transact())
    db = scope(port)
    ran: list[bool] = []

    def outer(_rtx: ReadOnlyTxnAttempt) -> str:
        with contextlib.suppress(RuntimeError):
            db.read_only(_raise_inner, itself)
        with pytest.raises(RollbackOnlyError):
            db.read_only(lambda _joined: ran.append(True), itself)
        return "withheld"

    with raises_contextualized(RollbackOnlyError) as excinfo:
        db.read_only(outer, itself)
    assert isinstance(excinfo.value.__cause__, RuntimeError)
    assert ran == []
    assert port.calls == [BeginCall("read_committed", "read_only"), RollbackCall()]


def test_an_escaped_read_only_attempt_refuses_every_read_after_it_ended() -> None:
    port = ScriptedAdapter(Transact())
    escaped: list[ReadOnlyTxnAttempt] = []
    scope(port).read_only(escaped.append, itself)
    with pytest.raises(EscapedTransactionError):
        escaped[0].read_rows(_account_seven())
    assert port.calls == [BeginCall("read_committed", "read_only"), CommitCall()]


def test_a_standalone_read_inside_a_read_only_callback_keeps_its_own_connection() -> None:
    port = ScriptedAdapter(Transact(Read(rows=[_NEW_ROW])))
    db = scope(port, options=TxnOptions(concurrency="locking"))

    def outer(_rtx: ReadOnlyTxnAttempt) -> int:
        return len(db.read_rows(_account_seven()).rows)

    assert db.read_only(outer, itself) == 1
    # Two acquisitions: the attempt's, and the standalone read's own, which
    # the active transaction never redirects onto its connection.
    assert port.acquisitions == 2


def test_a_read_only_attempt_replays_a_deadlocked_commit() -> None:
    port = ScriptedAdapter(Transact(commit=deadlock()), Transact())
    assert scope(port).read_only(lambda _rtx: "ok", itself) == "ok"
    assert port.calls.count(BeginCall("read_committed", "read_only")) == 2
