"""Caller-addressed patch and replacement through the public verbs (scripted port).

A target write names an existing object by key and states its own starting
revision. These tests grade what each call puts on the wire and when: the
Optimistic gate on the caller's version, the Locking acquisition and its reuse,
the empty patch that does nothing, the exact-window composition matrix with
observed writes, whole-group refusals that leave earlier work executable, the
attempt-wide refusal of an object the attempt inserted, and the
non-retriable precondition failure.
"""

from __future__ import annotations

import datetime as dt
import gc
import inspect
from collections.abc import Callable
from decimal import Decimal
from typing import Literal, cast

import pytest

from parallax.conformance.class_models import MODELS
from parallax.conformance.story_models import Wallet
from parallax.core import Attr, Entity, attr
from parallax.core.dialect import POSTGRES
from parallax.core.entity import DomainModel
from parallax.core.unit_work import (
    MissingTargetError,
    RollbackOnlyError,
    WriteInstructionError,
    WritePreconditionError,
    WriteRejectedError,
)
from parallax.snapshot.handle import Transaction, WriteEvidenceError
from parallax.snapshot.handle._wire import WireTransactionView
from tests._support import mirrored_models as mm
from tests._support.adoption import raises_contextualized
from tests._support.db_port import (
    BeginCall,
    CommitCall,
    PortCall,
    Read,
    ReadCall,
    RollbackCall,
    ScriptedAdapter,
    Transact,
    Write,
    WriteCall,
)
from tests.unit._transact_support import (
    FIND_SQL_LOCKED,
    FIND_SQL_UNLOCKED,
    FIXED,
    PAYMENT,
    account_db,
    db_for,
)

type _Representation = Literal["typed", "wire"]

_REPRESENTATIONS = pytest.mark.parametrize("representation", ["typed", "wire"])

_GATED = POSTGRES.to_driver_sql(
    "update account set owner = ?, balance = ?, version = ? where id = ? and version = ?"
)
_GATED_BALANCE = POSTGRES.to_driver_sql(
    "update account set balance = ?, version = ? where id = ? and version = ?"
)
_GATED_OWNER = POSTGRES.to_driver_sql(
    "update account set owner = ?, version = ? where id = ? and version = ?"
)
_UNGATED_BALANCE = POSTGRES.to_driver_sql(
    "update account set balance = ?, version = ? where id = ?"
)
_GATED_DELETE = POSTGRES.to_driver_sql("delete from account where id = ? and version = ?")
_WALLET_FIND_LOCKED = POSTGRES.to_driver_sql(
    "select t0.id, t0.owner, t0.balance from wallet t0 where t0.id = ? for share of t0"
)
_WALLET_UPDATE = POSTGRES.to_driver_sql("update wallet set balance = ? where id = ?")


_ACCOUNT_ONE = {
    "target": "Account",
    "predicate": {"eq": {"attr": "Account.id", "value": 1}},
}


def _row(version: int = 3, balance: str = "100.00") -> dict[str, object]:
    return {"id": 1, "owner": "Ada", "balance": Decimal(balance), "version": version}


def _patch(tx: Transaction, version: int = 3, **changes: object) -> None:
    tx.wire.update("Account", {"id": 1, **changes}, if_version=version)


def _replace(
    tx: Transaction, representation: _Representation, version: int = 3, owner: str = "Zed"
) -> None:
    if representation == "typed":
        tx.replace(mm.Account(id=1, owner=owner, balance=Decimal("3.00")), if_version=version)
    else:
        tx.wire.replace("Account", {"id": 1, "owner": owner, "balance": "3.00"}, if_version=version)


def _calls(port: ScriptedAdapter) -> list[PortCall]:
    return [call for call in port.calls if not isinstance(call, BeginCall | CommitCall)]


# --------------------------------------------------------------------------- #
# Optimistic: the caller's revision is the gate, and nothing is read.          #
# --------------------------------------------------------------------------- #
def test_a_wire_patch_gates_on_its_callers_version_and_reads_nothing() -> None:
    port = ScriptedAdapter(Transact(Write()))

    def fn(tx: Transaction) -> None:
        assert tx.wire.update("Account", {"id": 1, "balance": "175.00"}, if_version=3) is None

    account_db(port).transact(fn)
    assert _calls(port) == [WriteCall(_GATED_BALANCE, (Decimal("175.00"), 4, 1, 3))]


@_REPRESENTATIONS
def test_a_replacement_writes_every_writable_member_under_its_callers_version(
    representation: _Representation,
) -> None:
    port = ScriptedAdapter(Transact(Write()))
    account_db(port).transact(lambda tx: _replace(tx, representation))
    assert _calls(port) == [WriteCall(_GATED, ("Zed", Decimal("3.00"), 4, 1, 3))]


def test_a_net_equal_patch_chain_still_advances_the_version_once() -> None:
    port = ScriptedAdapter(Transact(Write()))

    def fn(tx: Transaction) -> None:
        _patch(tx, balance="150.00")
        _patch(tx, balance="100.00")

    account_db(port).transact(fn)
    assert _calls(port) == [WriteCall(_GATED_BALANCE, (Decimal("100.00"), 4, 1, 3))]


@pytest.mark.parametrize("concurrency", ["optimistic", "locking"])
def test_an_identity_only_patch_reads_writes_and_checks_nothing(
    concurrency: Literal["optimistic", "locking"],
) -> None:
    versioned = ScriptedAdapter(Transact())
    account_db(versioned).transact(
        lambda tx: tx.wire.update("Account", {"id": 1}, if_version=99), concurrency=concurrency
    )
    unversioned = ScriptedAdapter(Transact())
    db_for(MODELS["wallet"], unversioned).transact(
        lambda tx: tx.wire.update("Wallet", {"id": 5}), concurrency=concurrency
    )
    assert _calls(versioned) == _calls(unversioned) == []


def test_an_identity_only_patch_neither_cancels_nor_changes_earlier_work() -> None:
    port = ScriptedAdapter(Transact(Write()))

    def fn(tx: Transaction) -> None:
        _patch(tx, balance="150.00")
        tx.wire.update("Account", {"id": 1}, if_version=99)

    account_db(port).transact(fn)
    assert _calls(port) == [WriteCall(_GATED_BALANCE, (Decimal("150.00"), 4, 1, 3))]


@pytest.mark.parametrize("until", [FIXED, None], ids=["finite", "explicit-none"])
@pytest.mark.parametrize("operation", ["update", "replace-typed", "replace-wire"])
def test_a_non_temporal_target_refuses_until_before_an_empty_patch_is_dropped(
    operation: str, until: dt.datetime | None
) -> None:
    port = ScriptedAdapter(Transact())
    bound = cast("dt.datetime", until)

    def fn(tx: Transaction) -> None:
        with pytest.raises(WriteInstructionError, match="until"):
            if operation == "update":
                tx.wire.update("Account", {"id": 1}, until=bound, if_version=3)
            elif operation == "replace-typed":
                tx.replace(mm.Account(id=1, owner="Zed", balance=Decimal(1)), until=bound)
            else:
                tx.wire.replace("Account", {"id": 1, "owner": "Zed", "balance": "1"}, until=bound)

    account_db(port).transact(fn)
    assert _calls(port) == []


# --------------------------------------------------------------------------- #
# Locking: participation comes from pending or live evidence, else one locked #
# point read; the caller's revision is compared there and never gates.        #
# --------------------------------------------------------------------------- #
def test_a_locking_target_write_reads_its_row_under_the_shared_lock_once() -> None:
    port = ScriptedAdapter(Transact(Read(rows=[_row()]), Write()))

    def fn(tx: Transaction) -> None:
        _patch(tx, balance="150.00")
        _patch(tx, owner="Bo")

    account_db(port).transact(fn, concurrency="locking")
    assert _calls(port) == [
        ReadCall(FIND_SQL_LOCKED, (1,)),
        WriteCall(
            POSTGRES.to_driver_sql(
                "update account set owner = ?, balance = ?, version = ? where id = ?"
            ),
            ("Bo", Decimal("150.00"), 4, 1),
        ),
    ]


def test_a_locking_target_write_reuses_a_held_read_of_exactly_its_state() -> None:
    port = ScriptedAdapter(Transact(Read(rows=[_row()]), Write()))

    def fn(tx: Transaction) -> None:
        held = tx.find(mm.Account.where(mm.Account.id == 1)).result()
        _patch(tx, balance="150.00")
        assert held.version == 3

    account_db(port).transact(fn, concurrency="locking")
    assert _calls(port) == [
        ReadCall(FIND_SQL_LOCKED, (1,)),
        WriteCall(_UNGATED_BALANCE, (Decimal("150.00"), 4, 1)),
    ]


@pytest.mark.parametrize("stored", [[_row(version=2)], []], ids=["another-revision", "no-row"])
def test_a_locking_target_write_refuses_a_stale_or_missing_start_at_the_call(
    stored: list[dict[str, object]],
) -> None:
    port = ScriptedAdapter(Transact(Read(rows=stored), Write()))

    def fn(tx: Transaction) -> None:
        tx.insert(mm.Account(id=7, owner="Newton", balance=Decimal("5.00")))
        with pytest.raises(WritePreconditionError) as refused:
            _patch(tx, balance="150.00")
        assert (dict(refused.value.key), refused.value.expected) == ({"id": 1}, 3)

    account_db(port).transact(fn, concurrency="locking")
    assert [type(call) for call in _calls(port)] == [ReadCall, WriteCall]
    assert cast("WriteCall", _calls(port)[1]).sql.startswith("insert into account")


def test_a_locking_target_write_reuses_a_pending_observed_write_of_its_state() -> None:
    port = ScriptedAdapter(Transact(Read(rows=[_row()]), Write()))

    def fn(tx: Transaction) -> None:
        source = tx.find(mm.Account.where(mm.Account.id == 1)).result()
        tx.update(source.edit(owner="Bo"))
        del source
        gc.collect()
        _patch(tx, balance="150.00")

    account_db(port).transact(fn, concurrency="locking")
    assert _calls(port) == [
        ReadCall(FIND_SQL_LOCKED, (1,)),
        WriteCall(
            POSTGRES.to_driver_sql(
                "update account set owner = ?, balance = ?, version = ? where id = ?"
            ),
            ("Bo", Decimal("150.00"), 4, 1),
        ),
    ]


def test_a_spent_read_never_stands_in_for_a_locking_acquisition_and_a_fresh_one_does() -> None:
    port = ScriptedAdapter(
        Transact(
            Read(rows=[_row()]),
            Write(),
            Read(rows=[_row(version=4)]),
            Read(rows=[_row(version=4)]),
            Write(),
        )
    )

    def fn(tx: Transaction) -> None:
        source = tx.find(mm.Account.where(mm.Account.id == 1)).result()
        tx.update(source.edit(owner="Bo"))
        fresh = tx.find(mm.Account.where(mm.Account.id == 1)).result()
        with pytest.raises(WritePreconditionError):
            _patch(tx, version=3, balance="150.00")
        _patch(tx, version=4, balance="150.00")
        assert (source.version, fresh.version) == (3, 4)

    account_db(port).transact(fn, concurrency="locking")
    assert _calls(port)[2:] == [
        ReadCall(FIND_SQL_LOCKED, (1,)),
        ReadCall(FIND_SQL_LOCKED, (1,)),
        WriteCall(_UNGATED_BALANCE, (Decimal("150.00"), 5, 1)),
    ]


def test_a_released_read_leaves_a_locking_target_write_to_acquire_its_row() -> None:
    port = ScriptedAdapter(Transact(Read(rows=[_row()]), Read(rows=[_row()]), Write()))

    def fn(tx: Transaction) -> None:
        tx.find(mm.Account.where(mm.Account.id == 1)).result()
        gc.collect()
        _patch(tx, balance="150.00")

    account_db(port).transact(fn, concurrency="locking")
    assert _calls(port) == [
        ReadCall(FIND_SQL_LOCKED, (1,)),
        ReadCall(FIND_SQL_LOCKED, (1,)),
        WriteCall(_UNGATED_BALANCE, (Decimal("150.00"), 4, 1)),
    ]


def test_a_read_of_another_version_does_not_stand_in_for_the_callers() -> None:
    port = ScriptedAdapter(Transact(Read(rows=[_row(version=2)]), Read(rows=[_row(version=2)])))

    def fn(tx: Transaction) -> None:
        held = tx.find(mm.Account.where(mm.Account.id == 1)).result()
        with pytest.raises(WritePreconditionError):
            _patch(tx, balance="150.00")
        assert held.version == 2

    account_db(port).transact(fn, concurrency="locking")
    assert _calls(port) == [ReadCall(FIND_SQL_LOCKED, (1,)), ReadCall(FIND_SQL_LOCKED, (1,))]


def test_an_unversioned_target_takes_the_locking_fallback_and_misses_as_a_missing_target() -> None:
    port = ScriptedAdapter(
        Transact(Read(rows=[{"id": 5, "owner": "Ada", "balance": Decimal(1)}]), Write(affected=0))
    )

    def fn(tx: Transaction) -> None:
        tx.wire.update("Wallet", {"id": 5, "balance": "2.00"})

    with raises_contextualized(MissingTargetError, match="Wallet"):
        db_for(MODELS["wallet"], port).transact(fn)
    assert _calls(port)[:2] == [
        ReadCall(_WALLET_FIND_LOCKED, (5,)),
        WriteCall(_WALLET_UPDATE, (Decimal("2.00"), 5)),
    ]


def test_a_target_writes_window_outranks_its_revision_which_outranks_its_payload() -> None:
    port = ScriptedAdapter(Transact())
    unknown = {"id": 1, "nickname": "Bo"}

    def fn(tx: Transaction) -> None:
        refusals: list[str] = []
        for call in (
            lambda: tx.wire.update("Account", unknown, valid_from=FIXED),
            lambda: tx.wire.update("Account", unknown),
            lambda: tx.wire.update("Account", unknown, if_version=3),
            lambda: tx.wire.update("Account", {"id": 1}, if_tx_start=FIXED),
            lambda: tx.wire.replace("Account", {"id": 1, "owner": "Zed"}, if_version=3),
        ):
            with pytest.raises(ValueError) as refused:
                call()
            refusals.append(str(refused.value))
        window, missing, undeclared, misstated, incomplete = refusals
        assert "valid_from" in window
        assert "requires if_version" in missing
        assert "undeclared" in undeclared and "nickname" in undeclared
        assert "takes if_version, not if_tx_start" in misstated
        assert "balance" in incomplete

    account_db(port).transact(fn)
    assert _calls(port) == []


def test_an_unversioned_target_states_no_revision() -> None:
    port = ScriptedAdapter(Transact())

    def fn(tx: Transaction) -> None:
        with pytest.raises(WriteInstructionError, match="takes no revision argument"):
            tx.replace(Wallet(id=5, owner="Ada", balance=Decimal(1)), if_version=1)

    db_for(MODELS["wallet"], port).transact(fn)
    assert _calls(port) == []


# --------------------------------------------------------------------------- #
# Failure: a failed precondition is the caller's, never retried, and dooms.   #
# --------------------------------------------------------------------------- #
def test_a_failed_precondition_is_never_retried_even_with_conflict_retries_on() -> None:
    port = ScriptedAdapter(Transact(Write(affected=0)), Transact(Write()))

    with raises_contextualized(WritePreconditionError, match="expected revision 3"):
        account_db(port).transact(
            lambda tx: _patch(tx, balance="150.00"), retry_optimistic_conflicts=True
        )
    assert sum(isinstance(call, WriteCall) for call in port.calls) == 1
    assert RollbackCall() in port.calls


def test_a_caught_precondition_failure_still_rolls_the_attempt_back() -> None:
    port = ScriptedAdapter(Transact(Write(affected=0)))

    def fn(tx: Transaction) -> str:
        _patch(tx, balance="150.00")
        with pytest.raises(WritePreconditionError):
            tx.find(mm.Account.where(mm.Account.id == 2))
        return "withheld"

    with raises_contextualized(RollbackOnlyError):
        account_db(port).transact(fn)
    assert RollbackCall() in port.calls


def test_a_retried_attempt_states_the_same_callers_revision() -> None:
    other = {"id": 2, "owner": "Linus", "balance": Decimal(1), "version": 1}
    port = ScriptedAdapter(
        Transact(Read(rows=[other]), Write(), Write(affected=0)),
        Transact(Read(rows=[other]), Write(times=2)),
    )

    def fn(tx: Transaction) -> None:
        source = tx.find(mm.Account.where(mm.Account.id == 2)).result()
        _patch(tx, balance="150.00")
        tx.update(source.edit(owner="Bo"))

    account_db(port).transact(fn, retry_optimistic_conflicts=True)
    targets = [
        call for call in port.calls if isinstance(call, WriteCall) and call.sql == _GATED_BALANCE
    ]
    assert [call.binds for call in targets] == [(Decimal("150.00"), 4, 1, 3)] * 2


# --------------------------------------------------------------------------- #
# Exact-window composition with observed writes of the same state.            #
# --------------------------------------------------------------------------- #
type _Step = Callable[[Transaction, mm.Account], None]


def _p(tx: Transaction, _source: mm.Account) -> None:
    _patch(tx, balance="150.00")


def _r(tx: Transaction, _source: mm.Account) -> None:
    _replace(tx, "wire")


def _o(tx: Transaction, source: mm.Account) -> None:
    tx.update(source.edit(owner="Bo"))


def _d(tx: Transaction, source: mm.Account) -> None:
    tx.delete(source)


@pytest.mark.parametrize(
    "steps, statement",
    [
        pytest.param((_p, _p), WriteCall(_GATED_BALANCE, (Decimal("150.00"), 4, 1, 3)), id="P-P"),
        pytest.param((_p, _r), WriteCall(_GATED, ("Zed", Decimal("3.00"), 4, 1, 3)), id="P-R"),
        pytest.param((_r, _p), WriteCall(_GATED, ("Zed", Decimal("150.00"), 4, 1, 3)), id="R-P"),
        pytest.param((_r, _r), WriteCall(_GATED, ("Zed", Decimal("3.00"), 4, 1, 3)), id="R-R"),
        pytest.param((_p, _o), WriteCall(_GATED, ("Bo", Decimal("150.00"), 4, 1, 3)), id="P-O"),
        pytest.param((_o, _p), WriteCall(_GATED, ("Bo", Decimal("150.00"), 4, 1, 3)), id="O-P"),
        pytest.param((_r, _o), WriteCall(_GATED, ("Bo", Decimal("3.00"), 4, 1, 3)), id="R-O"),
        pytest.param((_o, _r), WriteCall(_GATED, ("Zed", Decimal("3.00"), 4, 1, 3)), id="O-R"),
        pytest.param((_p, _d), WriteCall(_GATED_DELETE, (1, 3)), id="P-D"),
        pytest.param((_r, _d), WriteCall(_GATED_DELETE, (1, 3)), id="R-D"),
        pytest.param(
            (_p, _o, _o), WriteCall(_GATED, ("Bo", Decimal("150.00"), 4, 1, 3)), id="P-O-O"
        ),
        pytest.param(
            (_r, _o, _p), WriteCall(_GATED, ("Bo", Decimal("150.00"), 4, 1, 3)), id="R-O-P"
        ),
        pytest.param((_o, _r, _d), WriteCall(_GATED_DELETE, (1, 3)), id="O-R-D"),
    ],
)
def test_exact_window_target_and_observed_writes_compose_into_one_statement(
    steps: tuple[_Step, ...], statement: WriteCall
) -> None:
    port = ScriptedAdapter(Transact(Read(rows=[_row()]), Write(), Read(rows=[])))
    spent: list[BaseException] = []

    def fn(tx: Transaction) -> None:
        source = tx.find(mm.Account.where(mm.Account.id == 1)).result()
        for step in steps:
            step(tx, source)
        tx.find(mm.Account.where(mm.Account.id == 2))
        with pytest.raises(WriteEvidenceError) as refused:
            tx.update(source.edit(owner="Again"))
        spent.append(refused.value)

    account_db(port).transact(fn)
    assert _calls(port)[1] == statement
    assert cast("WriteEvidenceError", spent[0]).code == "write-evidence-consumed"


def test_a_composed_write_whose_gate_fails_reports_the_callers_precondition() -> None:
    port = ScriptedAdapter(Transact(Read(rows=[_row()]), Write(affected=0)))

    def fn(tx: Transaction) -> None:
        source = tx.find(mm.Account.where(mm.Account.id == 1)).result()
        tx.update(source.edit(owner="Bo"))
        _patch(tx, balance="150.00")

    with raises_contextualized(WritePreconditionError):
        account_db(port).transact(fn, retry_optimistic_conflicts=True)


type _WalletStep = Callable[[Transaction, Wallet], None]


def _wallet_p(tx: Transaction, _source: Wallet) -> None:
    tx.wire.update("Wallet", {"id": 5, "balance": "2.00"})


def _wallet_r(tx: Transaction, _source: Wallet) -> None:
    tx.replace(Wallet(id=5, owner="Zed", balance=Decimal("3.00")))


def _wallet_o(tx: Transaction, source: Wallet) -> None:
    tx.update(source.edit(owner="Bo"))


def _wallet_d(tx: Transaction, source: Wallet) -> None:
    tx.delete(source)


_WALLET_ROW = {"id": 5, "owner": "Ada", "balance": Decimal(1)}
_WALLET_UPDATE_BOTH = POSTGRES.to_driver_sql(
    "update wallet set owner = ?, balance = ? where id = ?"
)
_WALLET_DELETE = POSTGRES.to_driver_sql("delete from wallet where id = ?")


@pytest.mark.parametrize(
    "steps, statement",
    [
        pytest.param(
            (_wallet_p, _wallet_r),
            WriteCall(_WALLET_UPDATE_BOTH, ("Zed", Decimal("3.00"), 5)),
            id="P-R",
        ),
        pytest.param(
            (_wallet_r, _wallet_p),
            WriteCall(_WALLET_UPDATE_BOTH, ("Zed", Decimal("2.00"), 5)),
            id="R-P",
        ),
        pytest.param(
            (_wallet_p, _wallet_o),
            WriteCall(_WALLET_UPDATE_BOTH, ("Bo", Decimal("2.00"), 5)),
            id="P-O",
        ),
        pytest.param(
            (_wallet_o, _wallet_p),
            WriteCall(_WALLET_UPDATE_BOTH, ("Bo", Decimal("2.00"), 5)),
            id="O-P",
        ),
        pytest.param(
            (_wallet_r, _wallet_o),
            WriteCall(_WALLET_UPDATE_BOTH, ("Bo", Decimal("3.00"), 5)),
            id="R-O",
        ),
        pytest.param(
            (_wallet_o, _wallet_r),
            WriteCall(_WALLET_UPDATE_BOTH, ("Zed", Decimal("3.00"), 5)),
            id="O-R",
        ),
        pytest.param((_wallet_p, _wallet_d), WriteCall(_WALLET_DELETE, (5,)), id="P-D"),
        pytest.param((_wallet_r, _wallet_d), WriteCall(_WALLET_DELETE, (5,)), id="R-D"),
    ],
)
def test_an_unversioned_target_composes_with_observed_writes_of_its_object(
    steps: tuple[_WalletStep, ...], statement: WriteCall
) -> None:
    # Unversioned rows take the Locking fallback: a target write arriving
    # first acquires its row, and one arriving after an observed write of the
    # object takes that write's participation instead.
    acquired = steps[0] in (_wallet_p, _wallet_r)
    acquisition = [Read(rows=[_WALLET_ROW])] if acquired else []
    port = ScriptedAdapter(Transact(Read(rows=[_WALLET_ROW]), *acquisition, Write(), Read(rows=[])))
    submitted = any(step in (_wallet_o, _wallet_d) for step in steps)

    def fn(tx: Transaction) -> None:
        source = tx.find(Wallet.where(Wallet.id == 5)).result()
        for step in steps:
            step(tx, source)
        tx.find(Wallet.where(Wallet.id == 6))
        if submitted:
            with pytest.raises(WriteEvidenceError, match="write-evidence-consumed"):
                tx.update(source.edit(owner="Again"))

    db_for(MODELS["wallet"], port).transact(fn)
    reads = [ReadCall(_WALLET_FIND_LOCKED, (5,))] * (2 if acquired else 1)
    assert _calls(port) == [*reads, statement, ReadCall(_WALLET_FIND_LOCKED, (6,))]


def test_an_unversioned_target_write_after_a_destruction_of_its_object_is_refused() -> None:
    port = ScriptedAdapter(Transact(Read(rows=[_WALLET_ROW]), Write()))

    def fn(tx: Transaction) -> None:
        source = tx.find(Wallet.where(Wallet.id == 5)).result()
        tx.delete(source)
        for second in (_wallet_p, _wallet_r):
            with pytest.raises(WriteEvidenceError, match="already buffered"):
                second(tx, source)

    db_for(MODELS["wallet"], port).transact(fn)
    assert _calls(port) == [ReadCall(_WALLET_FIND_LOCKED, (5,)), WriteCall(_WALLET_DELETE, (5,))]


@pytest.mark.parametrize("second", [_p, _r], ids=["D-P", "D-R"])
def test_a_target_write_after_a_destruction_of_its_state_is_refused(second: _Step) -> None:
    port = ScriptedAdapter(Transact(Read(rows=[_row()]), Write()))

    def fn(tx: Transaction) -> None:
        source = tx.find(mm.Account.where(mm.Account.id == 1)).result()
        tx.delete(source)
        with pytest.raises(WriteEvidenceError) as refused:
            second(tx, source)
        assert refused.value.code == "write-evidence-already-claimed"

    account_db(port).transact(fn)
    assert _calls(port)[1] == WriteCall(_GATED_DELETE, (1, 3))


# --------------------------------------------------------------------------- #
# Whole-group refusal: one object's writes start from one state.              #
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("concurrency", ["optimistic", "locking"])
def test_a_second_stated_revision_of_one_object_is_refused_and_the_first_still_runs(
    concurrency: Literal["optimistic", "locking"],
) -> None:
    acquired = [Read(rows=[_row()])] if concurrency == "locking" else []
    port = ScriptedAdapter(Transact(*acquired, Write()))

    def fn(tx: Transaction) -> None:
        _patch(tx, balance="150.00")
        with pytest.raises(WriteEvidenceError) as refused:
            _patch(tx, version=4, owner="Bo")
        assert refused.value.code == "write-evidence-already-claimed"

    account_db(port).transact(fn, concurrency=concurrency)
    assert _calls(port) == (
        [WriteCall(_GATED_BALANCE, (Decimal("150.00"), 4, 1, 3))]
        if concurrency == "optimistic"
        else [
            ReadCall(FIND_SQL_LOCKED, (1,)),
            WriteCall(_UNGATED_BALANCE, (Decimal("150.00"), 4, 1)),
        ]
    )


@pytest.mark.parametrize("target_first", [True, False], ids=["target-first", "observed-first"])
def test_a_target_and_an_observed_write_of_two_states_of_one_object_are_refused(
    target_first: bool,
) -> None:
    port = ScriptedAdapter(Transact(Read(rows=[_row(version=2)]), Write()))

    def fn(tx: Transaction) -> None:
        source = tx.find(mm.Account.where(mm.Account.id == 1)).result()
        first, second = (_p, _o) if target_first else (_o, _p)
        first(tx, source)
        with pytest.raises(WriteEvidenceError, match="already buffered"):
            second(tx, source)

    account_db(port).transact(fn)
    expected = (
        WriteCall(_GATED_BALANCE, (Decimal("150.00"), 4, 1, 3))
        if target_first
        else WriteCall(_GATED_OWNER, ("Bo", 3, 1, 2))
    )
    assert _calls(port)[1] == expected


def test_a_target_write_of_a_state_a_pending_group_selected_is_refused() -> None:
    port = ScriptedAdapter(Transact(Read(rows=[_row(version=2)]), Write()))

    def fn(tx: Transaction) -> None:
        tx.update_where(mm.Account.where(mm.Account.id == 1), mm.Account.owner.set("Bo"))
        with pytest.raises(WriteEvidenceError, match="already buffered"):
            _patch(tx, balance="150.00")

    account_db(port).transact(fn)
    assert [type(call) for call in _calls(port)] == [ReadCall, WriteCall]


# --------------------------------------------------------------------------- #
# An object this attempt inserted is written through its source until commit. #
# --------------------------------------------------------------------------- #
@_REPRESENTATIONS
@pytest.mark.parametrize("flushed", [False, True], ids=["pending", "after-a-helper-read"])
def test_a_target_write_of_an_object_this_attempt_inserted_is_refused(
    representation: _Representation, flushed: bool
) -> None:
    port = ScriptedAdapter(Transact(Write(), Read(rows=[]), Write()))

    def fn(tx: Transaction) -> None:
        inserted = mm.Account(id=1, owner="Ada", balance=Decimal("1.00"))
        tx.insert(inserted)
        if flushed:
            tx.find(mm.Account.where(mm.Account.id == 2))
        with pytest.raises(WriteEvidenceError) as refused:
            if representation == "typed":
                _replace(tx, "typed", version=1)
            else:
                _patch(tx, version=1, balance="2.00")
        assert refused.value.code == "write-evidence-inserted"
        tx.wire.update("Account", {"id": 1}, if_version=1)
        tx.update(inserted.edit(balance=Decimal("2.00")))

    account_db(port).transact(fn)
    assert [type(call) for call in _calls(port)] == (
        [WriteCall, ReadCall, WriteCall] if flushed else [WriteCall]
    )


def test_a_cancelled_insertion_of_an_object_still_refuses_a_target_write_of_it() -> None:
    port = ScriptedAdapter(Transact())

    def fn(tx: Transaction) -> None:
        inserted = mm.Account(id=1, owner="Ada", balance=Decimal("1.00"))
        tx.insert(inserted)
        tx.delete(inserted)
        with pytest.raises(WriteEvidenceError, match="inserted the object"):
            _patch(tx, version=1, balance="2.00")

    account_db(port).transact(fn)
    assert _calls(port) == []


def test_a_committed_object_rewritten_in_this_attempt_is_target_writable() -> None:
    port = ScriptedAdapter(Transact(Read(rows=[_row()]), Write(), Read(rows=[_row(4)]), Write()))

    def fn(tx: Transaction) -> None:
        source = tx.find(mm.Account.where(mm.Account.id == 1)).result()
        tx.update(source.edit(owner="Bo"))
        assert tx.find(mm.Account.where(mm.Account.id == 1)).result().version == 4
        _patch(tx, version=4, balance="150.00")

    account_db(port).transact(fn)
    assert _calls(port)[-1] == WriteCall(_GATED_BALANCE, (Decimal("150.00"), 5, 1, 4))


# --------------------------------------------------------------------------- #
# The two update overloads, addressing, subtypes, and keyword-only arguments. #
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("keyword", ["if_version", "if_tx_start", "valid_from"])
def test_an_observed_update_takes_its_condition_from_its_source(keyword: str) -> None:
    port = ScriptedAdapter(Transact(Read(rows=[_row()])))
    stated: dict[str, object] = {"if_version": 3, "if_tx_start": FIXED, "valid_from": FIXED}

    def fn(tx: Transaction) -> None:
        node = tx.wire.find(_ACCOUNT_ONE).result()
        update = cast("Callable[..., None]", tx.wire.update)
        with pytest.raises(WriteInstructionError, match="name its Entity instead"):
            update(node, {"balance": "1.00"}, **{keyword: stated[keyword]})

    account_db(port).transact(fn)


def test_a_typed_replacement_of_a_read_value_is_addressed_by_its_key_alone() -> None:
    port = ScriptedAdapter(Transact(Read(rows=[_row()]), Write()))

    def fn(tx: Transaction) -> None:
        fetched = tx.find(mm.Account.where(mm.Account.id == 1)).result()
        tx.replace(fetched.edit(owner="Bo"), if_version=7)

    account_db(port).transact(fn)
    assert _calls(port) == [
        ReadCall(FIND_SQL_UNLOCKED, (1,)),
        WriteCall(_GATED, ("Bo", Decimal("100.00"), 8, 1, 7)),
    ]


class Ledger(Entity, table="ledger", namespace="parallax.targetwrites"):
    id: Attr[int] = attr(primary_key=True)
    opened: Attr[str] = attr(read_only=True)
    note: Attr[str | None]
    version: Attr[int] = attr(optimistic_locking=True)


class KeyLedger(Entity, table="ledger", namespace="parallax.targetwrites"):
    id: Attr[int] = attr(primary_key=True, read_only=True)
    opened: Attr[str] = attr(read_only=True)
    note: Attr[str | None]
    version: Attr[int] = attr(optimistic_locking=True)


@pytest.mark.parametrize("entity", [Ledger, KeyLedger], ids=["key", "read-only-key"])
def test_a_typed_replacement_of_a_read_value_leaves_its_read_only_members_unwritten(
    entity: type[Ledger | KeyLedger],
) -> None:
    stored = {"id": 1, "opened": "2024-01-01", "note": "kept", "version": 3}
    port = ScriptedAdapter(Transact(Read(rows=[stored]), Write()))
    ledger = cast("type[Ledger]", entity)

    def fn(tx: Transaction) -> None:
        fetched = tx.find(ledger.where(ledger.id == 1)).result()
        tx.replace(fetched.edit(note="changed"), if_version=3)

    db_for(DomainModel(entity), port).transact(fn)
    write = _calls(port)[-1]
    assert write == WriteCall(
        POSTGRES.to_driver_sql(
            "update ledger set note = ?, version = ? where id = ? and version = ?"
        ),
        ("changed", 4, 1, 3),
    )


def test_a_subtype_target_write_is_guarded_by_its_tag_and_refuses_a_sibling_member() -> None:
    port = ScriptedAdapter(
        Transact(Read(rows=[{"id": 4, "amount": Decimal(1), "cardNetwork": "visa"}]), Write())
    )

    def fn(tx: Transaction) -> None:
        with pytest.raises(WriteRejectedError):
            tx.wire.update("CardPayment", {"id": 4, "tendered": "1.00"})
        tx.wire.update("CardPayment", {"id": 4, "cardNetwork": "amex"})

    db_for(PAYMENT, port).transact(fn)
    read, write = _calls(port)
    assert isinstance(read, ReadCall) and "kind" in read.sql and "for share" in read.sql
    assert isinstance(write, WriteCall) and write.sql.endswith("where id = %s and kind = %s")
    assert write.binds == ("amex", 4, "card")


@pytest.mark.parametrize(
    "method",
    [Transaction.replace, WireTransactionView.replace, WireTransactionView.update],
    ids=["typed-replace", "wire-replace", "wire-update"],
)
def test_a_target_writes_revision_and_bounds_are_keyword_only(method: Callable[..., None]) -> None:
    parameters = inspect.signature(method).parameters
    for name in ("valid_from", "until", "if_version", "if_tx_start"):
        assert parameters[name].kind is inspect.Parameter.KEYWORD_ONLY
    assert parameters["if_version"].default is None
    assert parameters["if_tx_start"].default is None
