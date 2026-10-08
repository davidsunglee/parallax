"""Non-Temporal writes on either side of a readless predicate write, through the
public verbs (scripted port)."""

from __future__ import annotations

from decimal import Decimal

import pytest

from parallax.conformance.story_models import Account, Wallet
from parallax.core.dialect import POSTGRES
from parallax.core.entity import DomainModel
from parallax.core.unit_work import Concurrency
from parallax.snapshot import Transaction
from tests._support.db_port import (
    BeginCall,
    CommitCall,
    PortCall,
    Read,
    ReadCall,
    ScriptedAdapter,
    Transact,
    Write,
    WriteCall,
)
from tests.unit._transact_support import FIND_SQL_LOCKED, FIND_SQL_UNLOCKED, db_for

_MODEL = DomainModel(Account, Wallet)

_WALLET_FIND = POSTGRES.to_driver_sql(
    "select t0.id, t0.owner, t0.balance from wallet t0 where t0.id = ? for share of t0"
)
_WALLET_BALANCE = POSTGRES.to_driver_sql("update wallet set balance = ? where id = ?")
_WALLET_INSERT = POSTGRES.to_driver_sql("insert into wallet(id, owner, balance) values (?, ?, ?)")
_WALLET_DELETE = POSTGRES.to_driver_sql("delete from wallet where id = ?")
_BARRIER = POSTGRES.to_driver_sql("update wallet set owner = ? where balance < ?")
_ACCOUNT_INSERT = POSTGRES.to_driver_sql(
    "insert into account(id, owner, balance, version) values (?, ?, ?, ?)"
)


def _account_update(member: str, *, gated: bool) -> str:
    gate = " and version = ?" if gated else ""
    return POSTGRES.to_driver_sql(
        f"update account set {member} = ?, version = ? where id = ?{gate}"
    )


def _calls(port: ScriptedAdapter) -> list[PortCall]:
    return [call for call in port.calls if not isinstance(call, BeginCall | CommitCall)]


def _barrier(tx: Transaction) -> None:
    tx.amend_where(Wallet.where(Wallet.balance < Decimal("2.00")), Wallet.owner.set("Low"))


_WALLET = {"id": 1, "owner": "Ada", "balance": Decimal("5.00")}
_ACCOUNT = {"id": 1, "owner": "Ada", "balance": Decimal("5.00"), "version": 3}


def test_a_write_of_one_state_on_each_side_of_a_barrier_executes_on_its_own_side() -> None:
    port = ScriptedAdapter(Transact(Read(rows=[_WALLET]), Write(times=3)))

    def fn(tx: Transaction) -> None:
        wallet = tx.find(Wallet.where(Wallet.id == 1)).result()
        tx.amend(wallet.edit(balance=Decimal("1.00")))
        _barrier(tx)
        tx.amend(wallet.edit(balance=Decimal("7.00")))

    db_for(_MODEL, port).transact(fn)
    assert _calls(port) == [
        ReadCall(_WALLET_FIND, (1,)),
        WriteCall(_WALLET_BALANCE, (Decimal("1.00"), 1)),
        WriteCall(_BARRIER, ("Low", Decimal("2.00"))),
        WriteCall(_WALLET_BALANCE, (Decimal("7.00"), 1)),
    ]


def test_writes_of_one_state_on_one_side_of_a_barrier_still_coalesce() -> None:
    port = ScriptedAdapter(Transact(Read(rows=[_WALLET]), Write(times=2)))

    def fn(tx: Transaction) -> None:
        wallet = tx.find(Wallet.where(Wallet.id == 1)).result()
        _barrier(tx)
        tx.amend(wallet.edit(balance=Decimal("1.00")))
        tx.amend(wallet.edit(owner="Bo"))

    db_for(_MODEL, port).transact(fn)
    assert _calls(port) == [
        ReadCall(_WALLET_FIND, (1,)),
        WriteCall(_BARRIER, ("Low", Decimal("2.00"))),
        WriteCall(
            POSTGRES.to_driver_sql("update wallet set owner = ?, balance = ? where id = ?"),
            ("Bo", Decimal("1.00"), 1),
        ),
    ]


@pytest.mark.parametrize(
    ("concurrency", "find"), [("optimistic", FIND_SQL_UNLOCKED), ("locking", FIND_SQL_LOCKED)]
)
def test_a_versioned_write_after_a_barrier_starts_from_the_version_the_earlier_one_left(
    concurrency: Concurrency, find: str
) -> None:
    port = ScriptedAdapter(Transact(Read(rows=[_ACCOUNT]), Write(times=3)))
    gated = concurrency == "optimistic"

    def fn(tx: Transaction) -> None:
        account = tx.find(Account.where(Account.id == 1)).result()
        tx.amend(account.edit(balance=Decimal("1.00")))
        _barrier(tx)
        tx.amend(account.edit(owner="Bo"))

    db_for(_MODEL, port).transact(fn, concurrency=concurrency)
    assert _calls(port) == [
        ReadCall(find, (1,)),
        WriteCall(
            _account_update("balance", gated=gated),
            (Decimal("1.00"), 4, 1, 3) if gated else (Decimal("1.00"), 4, 1),
        ),
        WriteCall(_BARRIER, ("Low", Decimal("2.00"))),
        WriteCall(
            _account_update("owner", gated=gated), ("Bo", 5, 1, 4) if gated else ("Bo", 5, 1)
        ),
    ]


def test_a_destruction_after_a_barrier_removes_the_version_the_earlier_write_left() -> None:
    port = ScriptedAdapter(Transact(Read(rows=[_ACCOUNT]), Write(times=3)))

    def fn(tx: Transaction) -> None:
        account = tx.find(Account.where(Account.id == 1)).result()
        tx.amend(account.edit(balance=Decimal("1.00")))
        _barrier(tx)
        tx.delete(account)

    db_for(_MODEL, port).transact(fn)
    assert _calls(port)[1:] == [
        WriteCall(_account_update("balance", gated=True), (Decimal("1.00"), 4, 1, 3)),
        WriteCall(_BARRIER, ("Low", Decimal("2.00"))),
        WriteCall(
            POSTGRES.to_driver_sql("delete from account where id = ? and version = ?"), (1, 4)
        ),
    ]


def test_a_chain_across_two_barriers_advances_once_per_side() -> None:
    port = ScriptedAdapter(Transact(Read(rows=[_ACCOUNT]), Write(times=5)))

    def fn(tx: Transaction) -> None:
        account = tx.find(Account.where(Account.id == 1)).result()
        tx.amend(account.edit(balance=Decimal("1.00")))
        _barrier(tx)
        tx.amend(account.edit(owner="Bo"))
        _barrier(tx)
        tx.amend(account.edit(owner="Cy"))

    db_for(_MODEL, port).transact(fn)
    writes = [call for call in _calls(port) if isinstance(call, WriteCall)]
    assert [call.binds for call in writes if call.sql != _BARRIER] == [
        (Decimal("1.00"), 4, 1, 3),
        ("Bo", 5, 1, 4),
        ("Cy", 6, 1, 5),
    ]


@pytest.mark.parametrize("representation", ["typed", "wire"])
def test_a_write_of_a_pending_insert_after_a_barrier_revises_the_row_it_opened(
    representation: str,
) -> None:
    port = ScriptedAdapter(Transact(Write(times=3)))

    def fn(tx: Transaction) -> None:
        if representation == "typed":
            wallet = Wallet(id=9, owner="Eve", balance=Decimal("1.00"))
            tx.insert(wallet)
            _barrier(tx)
            tx.amend(wallet.edit(balance=Decimal("7.00")))
        else:
            node = tx.wire.insert("Wallet", {"id": 9, "owner": "Eve", "balance": "1.00"})
            _barrier(tx)
            tx.wire.amend(node, {"balance": "7.00"})

    db_for(_MODEL, port).transact(fn)
    assert _calls(port) == [
        WriteCall(_WALLET_INSERT, (9, "Eve", Decimal("1.00"))),
        WriteCall(_BARRIER, ("Low", Decimal("2.00"))),
        WriteCall(_WALLET_BALANCE, (Decimal("7.00"), 9)),
    ]


def test_a_versioned_pending_insert_is_revised_after_a_barrier_from_its_first_version() -> None:
    port = ScriptedAdapter(Transact(Write(times=5)))

    def fn(tx: Transaction) -> None:
        account = Account(id=9, owner="Eve", balance=Decimal("1.00"))
        tx.insert(account)
        _barrier(tx)
        edited = account.edit(balance=Decimal("7.00"))
        tx.amend(edited)
        _barrier(tx)
        tx.amend(edited.edit(owner="Fay"))

    db_for(_MODEL, port).transact(fn)
    assert _calls(port) == [
        WriteCall(_ACCOUNT_INSERT, (9, "Eve", Decimal("1.00"), 1)),
        WriteCall(_BARRIER, ("Low", Decimal("2.00"))),
        WriteCall(_account_update("balance", gated=True), (Decimal("7.00"), 2, 9, 1)),
        WriteCall(_BARRIER, ("Low", Decimal("2.00"))),
        WriteCall(
            POSTGRES.to_driver_sql(
                "update account set owner = ?, balance = ?, version = ? where id = ? "
                "and version = ?"
            ),
            ("Fay", Decimal("7.00"), 3, 9, 2),
        ),
    ]


def test_a_pending_insert_removed_after_a_barrier_executes_and_admits_a_reinsertion() -> None:
    port = ScriptedAdapter(Transact(Write(times=4)))

    def fn(tx: Transaction) -> None:
        wallet = Wallet(id=9, owner="Eve", balance=Decimal("1.00"))
        tx.insert(wallet)
        _barrier(tx)
        tx.delete(wallet)
        tx.insert(Wallet(id=9, owner="Gus", balance=Decimal("3.00")))

    db_for(_MODEL, port).transact(fn)
    assert _calls(port) == [
        WriteCall(_WALLET_INSERT, (9, "Eve", Decimal("1.00"))),
        WriteCall(_BARRIER, ("Low", Decimal("2.00"))),
        WriteCall(_WALLET_DELETE, (9,)),
        WriteCall(_WALLET_INSERT, (9, "Gus", Decimal("3.00"))),
    ]


def test_a_pending_insert_and_its_removal_before_a_barrier_still_cancel() -> None:
    port = ScriptedAdapter(Transact(Write()))

    def fn(tx: Transaction) -> None:
        wallet = Wallet(id=9, owner="Eve", balance=Decimal("1.00"))
        tx.insert(wallet)
        tx.delete(wallet)
        _barrier(tx)

    db_for(_MODEL, port).transact(fn)
    assert _calls(port) == [WriteCall(_BARRIER, ("Low", Decimal("2.00")))]


def test_a_target_write_after_a_barrier_states_the_version_the_earlier_one_left() -> None:
    port = ScriptedAdapter(Transact(Write(times=3)))

    def fn(tx: Transaction) -> None:
        tx.wire.amend_if("Account", {"id": 1, "balance": "1.00"}, version=3)
        _barrier(tx)
        tx.wire.amend_if("Account", {"id": 1, "owner": "Bo"}, version=3)

    db_for(_MODEL, port).transact(fn)
    assert _calls(port) == [
        WriteCall(_account_update("balance", gated=True), (Decimal("1.00"), 4, 1, 3)),
        WriteCall(_BARRIER, ("Low", Decimal("2.00"))),
        WriteCall(_account_update("owner", gated=True), ("Bo", 5, 1, 4)),
    ]
