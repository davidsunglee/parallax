"""Typed write failures through ``ScopedDatabase.transact`` (`execution.md`,
Docker-free fake ports).

The runner's own semantics — joins, options, isolation, retry bounds, boundary
outcomes, and adoption — are graded over the neutral scope and Attempt in
``tests/unit/core/execution/test_runner.py``. What stays here is what only the
Typed write verbs reach: the write-effect failure a real flush of a Typed
update raises, which of them the ``retry_optimistic_conflicts`` opt-in widens
the retriable set to, a caught flush failure dooming the attempt, a failed unit
stopping the flush, the participating read's lock under the root's preference,
and the write-evidence strategy each attempt's adopted selection settles a
Typed keyed write under.
"""

from __future__ import annotations

import contextlib
import re
from collections.abc import Callable
from decimal import Decimal

import pytest

from parallax.conformance.scripted_clock import FixedClock
from parallax.core import Attr, DomainModel, Entity, attr, index
from parallax.core.db_port import DatabaseAdapter
from parallax.core.execution import DatabaseOptions, ServingModel, prepare_model
from parallax.core.unit_work import (
    CardinalityCorruptionError,
    MissingTargetError,
    OptimisticLockConflictError,
    RollbackOnlyError,
    StaleWriteError,
    WriteEvidenceError,
)
from parallax.snapshot import Database, ScopedDatabase, Transaction
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
    WriteCall,
)
from tests._support.root_ownership import own_root
from tests.unit._transact_support import (
    ACCOUNT,
    FIXED,
    PERSON,
    account_db,
    db_for,
    deadlock,
    grace,
)

_A = prepare_model(ACCOUNT, edition="a")


def _serving_db(port: DatabaseAdapter, serving: ServingModel) -> ScopedDatabase:
    return own_root(Database.connect(port, serving, clock=FixedClock(FIXED))).using_database_login()


def _configured_db(port: DatabaseAdapter, options: DatabaseOptions) -> ScopedDatabase:
    return own_root(
        Database.connect(port, ACCOUNT, options=options, clock=FixedClock(FIXED))
    ).using_database_login()


class _UnversionedAccount(
    Entity,
    table="account",
    name="Account",
    namespace="parallax.compatibility",
    indices=(index("account_owner", "owner"),),
):
    """``ACCOUNT``'s Entity without its version Attribute, so the default
    preference resolves it to the Locking strategy rather than Optimistic."""

    id: Attr[int] = attr(primary_key=True)
    owner: Attr[str] = attr(max_length=64)
    balance: Attr[Decimal] = attr(precision=18, scale=2)


_UNVERSIONED = prepare_model(DomainModel(_UnversionedAccount), edition="unversioned")


def _refusing_strategy(delete: Callable[[], object]) -> str:
    """The strategy named by the refusal of a keyed delete whose value no read produced."""
    with pytest.raises(WriteEvidenceError) as refusal:
        delete()
    assert refusal.value.code == "write-evidence-unavailable"
    named = re.search(r"the (\w+) strategy", refusal.value.message)
    assert named is not None
    return named.group(1)


def test_each_attempt_settles_write_evidence_under_its_adopted_selection() -> None:
    serving = ServingModel(_A)
    port = ScriptedAdapter(Transact(commit=deadlock()), Transact())
    db = _serving_db(port, serving)
    seen: list[str] = []

    def body(tx: Transaction) -> None:
        if seen:
            unread = _UnversionedAccount(id=3, owner="Grace", balance=Decimal("10.00"))
            seen.append(_refusing_strategy(lambda: tx.delete(unread)))
            return
        seen.append(_refusing_strategy(lambda: tx.delete(grace())))
        serving.publish(_UNVERSIONED, expected=_A)
        db.transact(lambda inner: seen.append(_refusing_strategy(lambda: inner.delete(grace()))))

    db.transact(body)
    assert seen == ["Optimistic", "Optimistic", "Locking"]
    assert not any(isinstance(op, WriteCall) for op in port.calls)


def _observe_and_update(tx: Transaction) -> None:
    current = tx.find(mm.Account.where(mm.Account.id == 3)).result()
    tx.amend(current.edit(balance=Decimal("20.00")))


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
    tx.amend(fetched.edit(name="Grace"))


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
    tx.amend(current.edit(balance=Decimal("20.00")))
    tx.find(mm.Account.where(mm.Account.id == 3))  # forces the flush inside THIS (joined) scope


def test_optimistic_conflict_rollback_only_cause_is_retried_with_the_opt_in() -> None:
    # The join rule extended to an optimistic-lock conflict (pinned
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


def _update_force_flush_and_catch(refusals: list[BaseException]) -> Callable[[Transaction], str]:
    def callback(tx: Transaction) -> str:
        _observe_and_update(tx)
        with contextlib.suppress(OptimisticLockConflictError):
            tx.find(mm.Account.where(mm.Account.id == 3))  # the flush this forces conflicts
        with pytest.raises(RollbackOnlyError) as refused:
            tx.find(mm.Account.where(mm.Account.id == 3))
        refusals.append(refused.value)
        return "caught"

    return callback


def test_a_caught_dependent_read_flush_failure_refuses_further_work_and_the_commit() -> None:
    # The OUTER callback catches its own forced flush's conflict: no joined
    # scope is involved, yet the attempt is doomed before the failure escapes the
    # read, so the next read is refused, the callback's value is withheld, and
    # nothing commits.
    grace = [{"id": 3, "owner": "Grace", "balance": Decimal("10.00"), "version": 1}]
    port = ScriptedAdapter(Transact(Read(rows=grace), Write(affected=0)))
    refusals: list[BaseException] = []
    with raises_contextualized(RollbackOnlyError) as failure:
        account_db(port).transact(_update_force_flush_and_catch(refusals), concurrency="optimistic")
    assert isinstance(failure.value.__cause__, OptimisticLockConflictError)
    (refusal,) = refusals
    assert isinstance(refusal.__cause__, OptimisticLockConflictError)
    assert port.calls.count(CommitCall()) == 0
    assert port.calls.count(RollbackCall()) == 1


def test_a_caught_flush_conflict_keeps_its_retriability_through_the_doom() -> None:
    grace = [{"id": 3, "owner": "Grace", "balance": Decimal("10.00"), "version": 1}]
    port = ScriptedAdapter(
        Transact(Read(rows=grace), Write(affected=0)),
        Transact(Read(rows=grace), Write(), Read(rows=grace)),
    )
    refusals: list[BaseException] = []

    def callback(tx: Transaction) -> str:
        if not refusals:
            return _update_force_flush_and_catch(refusals)(tx)
        _observe_and_update(tx)
        tx.find(mm.Account.where(mm.Account.id == 3))
        return "retried"

    db = account_db(port)
    assert (
        db.transact(callback, concurrency="optimistic", retry_optimistic_conflicts=True)
        == "retried"
    )
    assert port.calls.count(BeginCall()) == 2


def test_a_failed_unit_stops_the_flush_before_any_later_unit_executes() -> None:
    rows = [
        {"id": 3, "owner": "Grace", "balance": Decimal("10.00"), "version": 1},
        {"id": 4, "owner": "Ada", "balance": Decimal("20.00"), "version": 1},
    ]
    port = ScriptedAdapter(Transact(Read(rows=rows), Write(affected=0)))

    def callback(tx: Transaction) -> None:
        for current in tx.find(mm.Account.where(mm.Account.id >= 3)).results():
            tx.amend(current.edit(balance=Decimal("30.00")))

    with raises_contextualized(OptimisticLockConflictError):
        account_db(port).transact(callback, concurrency="optimistic")
    assert sum(isinstance(call, WriteCall) for call in port.calls) == 1


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
