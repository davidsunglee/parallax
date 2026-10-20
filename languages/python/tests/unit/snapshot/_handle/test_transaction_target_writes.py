"""Caller-addressed patch, replacement, and deletion through the public verbs
(scripted port).

A target write names an existing object by key and states its own starting
revision. These tests grade what each call puts on the wire and when: the
Optimistic gate on the caller's version, the Locking acquisition and its reuse,
the empty patch that does nothing beside the deletion that is never empty, the
exact-window composition matrix with observed writes, whole-group refusals that
leave earlier work executable, the attempt-wide refusal of an object the
attempt inserted, and the non-retriable precondition failure.
"""

from __future__ import annotations

import gc
import inspect
from collections.abc import Callable
from decimal import Decimal
from typing import Literal, cast

import pytest

from parallax.core import Attr, Entity, attr
from parallax.core._execution._options import OMITTED
from parallax.core.dialect import POSTGRES
from parallax.core.entity import DomainModel
from parallax.core.unit_work import (
    RollbackOnlyError,
    WriteEvidenceError,
    WritePreconditionError,
    WriteRejectedError,
)
from parallax.snapshot import TxnContext
from parallax.snapshot._handle._wire import WireTransactionView
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
    account_db,
    db_for,
)
from tests.unit.snapshot._handle._vessel_model import VESSEL

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
_UNGATED_DELETE = POSTGRES.to_driver_sql("delete from account where id = ?")


_ACCOUNT_ONE = {
    "target": "Account",
    "predicate": {"eq": {"path": "Account.id", "value": 1}},
}


def _row(version: int = 3, balance: str = "100.00") -> dict[str, object]:
    return {"id": 1, "owner": "Ada", "balance": Decimal(balance), "version": version}


def _patch(tx: TxnContext, version: int = 3, **changes: object) -> None:
    tx.wire.amend_if("Account", {"id": 1, **changes}, version=version)


def _delete(tx: TxnContext, representation: _Representation = "wire", version: int = 3) -> None:
    if representation == "typed":
        tx.delete_if(mm.Account, key=1, version=version)
    else:
        tx.wire.delete_if("Account", {"id": 1}, version=version)


def _replace(
    tx: TxnContext, representation: _Representation, version: int = 3, owner: str = "Zed"
) -> None:
    if representation == "typed":
        tx.replace_if(mm.Account(id=1, owner=owner, balance=Decimal("3.00")), version=version)
    else:
        tx.wire.replace_if("Account", {"id": 1, "owner": owner, "balance": "3.00"}, version=version)


def _calls(port: ScriptedAdapter) -> list[PortCall]:
    return [call for call in port.calls if not isinstance(call, BeginCall | CommitCall)]


# --------------------------------------------------------------------------- #
# Optimistic: the caller's revision is the gate, and nothing is read.          #
# --------------------------------------------------------------------------- #
def test_a_wire_patch_gates_on_its_callers_version_and_reads_nothing() -> None:
    port = ScriptedAdapter(Transact(Write()))

    def fn(tx: TxnContext) -> None:
        assert tx.wire.amend_if("Account", {"id": 1, "balance": "175.00"}, version=3) is None

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

    def fn(tx: TxnContext) -> None:
        _patch(tx, balance="150.00")
        _patch(tx, balance="100.00")

    account_db(port).transact(fn)
    assert _calls(port) == [WriteCall(_GATED_BALANCE, (Decimal("100.00"), 4, 1, 3))]


@_REPRESENTATIONS
def test_a_deletion_gates_on_its_callers_version_and_reads_nothing(
    representation: _Representation,
) -> None:
    port = ScriptedAdapter(Transact(Write()))

    def fn(tx: TxnContext) -> None:
        _delete(tx, representation)
        assert _calls(port) == []

    account_db(port).transact(fn)
    assert _calls(port) == [WriteCall(_GATED_DELETE, (1, 3))]


@_REPRESENTATIONS
def test_a_deletion_that_removes_nothing_fails_its_precondition_and_never_commits(
    representation: _Representation,
) -> None:
    port = ScriptedAdapter(Transact(Write(affected=0)))

    with raises_contextualized(WritePreconditionError, match="expected revision 3") as failed:
        account_db(port).transact(lambda tx: _delete(tx, representation))
    assert dict(failed.value.key) == {"id": 1}
    assert _calls(port) == [WriteCall(_GATED_DELETE, (1, 3)), RollbackCall()]


def test_an_identity_only_patch_neither_cancels_nor_changes_earlier_work() -> None:
    port = ScriptedAdapter(Transact(Write()))

    def fn(tx: TxnContext) -> None:
        _patch(tx, balance="150.00")
        tx.wire.amend_if("Account", {"id": 1}, version=99)

    account_db(port).transact(fn)
    assert _calls(port) == [WriteCall(_GATED_BALANCE, (Decimal("150.00"), 4, 1, 3))]


# --------------------------------------------------------------------------- #
# Locking: participation comes from pending or live evidence, else one locked #
# point read; the caller's revision is compared there and never gates.        #
# --------------------------------------------------------------------------- #
def test_a_locking_target_write_reads_its_row_under_the_shared_lock_once() -> None:
    port = ScriptedAdapter(Transact(Read(rows=[_row()]), Write()))

    def fn(tx: TxnContext) -> None:
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

    def fn(tx: TxnContext) -> None:
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

    def fn(tx: TxnContext) -> None:
        tx.insert(mm.Account(id=7, owner="Newton", balance=Decimal("5.00")))
        with pytest.raises(WritePreconditionError) as refused:
            _patch(tx, balance="150.00")
        assert (dict(refused.value.key), refused.value.expected) == ({"id": 1}, 3)

    account_db(port).transact(fn, concurrency="locking")
    assert [type(call) for call in _calls(port)] == [ReadCall, WriteCall]
    assert cast("WriteCall", _calls(port)[1]).sql.startswith("insert into account")


def test_a_locking_target_write_reuses_a_pending_observed_write_of_its_state() -> None:
    port = ScriptedAdapter(Transact(Read(rows=[_row()]), Write()))

    def fn(tx: TxnContext) -> None:
        source = tx.find(mm.Account.where(mm.Account.id == 1)).result()
        tx.amend(source.edit(owner="Bo"))
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

    def fn(tx: TxnContext) -> None:
        source = tx.find(mm.Account.where(mm.Account.id == 1)).result()
        tx.amend(source.edit(owner="Bo"))
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

    def fn(tx: TxnContext) -> None:
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

    def fn(tx: TxnContext) -> None:
        held = tx.find(mm.Account.where(mm.Account.id == 1)).result()
        with pytest.raises(WritePreconditionError):
            _patch(tx, balance="150.00")
        assert held.version == 2

    account_db(port).transact(fn, concurrency="locking")
    assert _calls(port) == [ReadCall(FIND_SQL_LOCKED, (1,)), ReadCall(FIND_SQL_LOCKED, (1,))]


@_REPRESENTATIONS
def test_a_locking_deletion_reads_its_row_under_the_shared_lock_and_deletes_ungated(
    representation: _Representation,
) -> None:
    port = ScriptedAdapter(Transact(Read(rows=[_row()]), Write()))

    def fn(tx: TxnContext) -> None:
        _delete(tx, representation)
        assert _calls(port) == [ReadCall(FIND_SQL_LOCKED, (1,))]

    account_db(port).transact(fn, concurrency="locking")
    assert _calls(port) == [ReadCall(FIND_SQL_LOCKED, (1,)), WriteCall(_UNGATED_DELETE, (1,))]


@pytest.mark.parametrize("stored", [[_row(version=2)], []], ids=["another-revision", "no-row"])
def test_a_locking_deletion_refuses_a_stale_or_missing_start_at_the_call(
    stored: list[dict[str, object]],
) -> None:
    port = ScriptedAdapter(Transact(Read(rows=stored)))

    def fn(tx: TxnContext) -> None:
        with pytest.raises(WritePreconditionError) as refused:
            _delete(tx)
        assert (dict(refused.value.key), refused.value.expected) == ({"id": 1}, 3)

    account_db(port).transact(fn, concurrency="locking")
    assert _calls(port) == [ReadCall(FIND_SQL_LOCKED, (1,))]


# --------------------------------------------------------------------------- #
# Failure: a failed precondition is the caller's, never retried, and dooms.   #
# --------------------------------------------------------------------------- #
def test_a_failed_precondition_is_never_retried_even_with_conflict_retries_on() -> None:
    port = ScriptedAdapter(Transact(Write(affected=0)), Transact(Write()))

    with raises_contextualized(WritePreconditionError, match="expected revision 3"):
        account_db(port).transact(lambda tx: _patch(tx, balance="150.00"))
    assert sum(isinstance(call, WriteCall) for call in port.calls) == 1
    assert RollbackCall() in port.calls


def test_a_caught_precondition_failure_still_rolls_the_attempt_back() -> None:
    port = ScriptedAdapter(Transact(Write(affected=0)))

    def fn(tx: TxnContext) -> str:
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

    def fn(tx: TxnContext) -> None:
        source = tx.find(mm.Account.where(mm.Account.id == 2)).result()
        _patch(tx, balance="150.00")
        tx.amend(source.edit(owner="Bo"))

    account_db(port).transact(fn)
    targets = [
        call for call in port.calls if isinstance(call, WriteCall) and call.sql == _GATED_BALANCE
    ]
    assert [call.binds for call in targets] == [(Decimal("150.00"), 4, 1, 3)] * 2


# --------------------------------------------------------------------------- #
# Exact-window composition with observed writes of the same state.            #
# --------------------------------------------------------------------------- #
type _Step = Callable[[TxnContext, mm.Account], None]


def _p(tx: TxnContext, _source: mm.Account) -> None:
    _patch(tx, balance="150.00")


def _r(tx: TxnContext, _source: mm.Account) -> None:
    _replace(tx, "wire")


def _o(tx: TxnContext, source: mm.Account) -> None:
    tx.amend(source.edit(owner="Bo"))


def _d(tx: TxnContext, source: mm.Account) -> None:
    tx.delete(source)


def _x(tx: TxnContext, _source: mm.Account) -> None:
    _delete(tx)


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
        pytest.param((_p, _x), WriteCall(_GATED_DELETE, (1, 3)), id="P-X"),
        pytest.param((_r, _x), WriteCall(_GATED_DELETE, (1, 3)), id="R-X"),
        pytest.param((_o, _x), WriteCall(_GATED_DELETE, (1, 3)), id="O-X"),
        pytest.param((_d, _x), WriteCall(_GATED_DELETE, (1, 3)), id="D-X"),
        pytest.param((_x, _d), WriteCall(_GATED_DELETE, (1, 3)), id="X-D"),
        pytest.param((_x, _x), WriteCall(_GATED_DELETE, (1, 3)), id="X-X"),
    ],
)
def test_exact_window_target_and_observed_writes_compose_into_one_statement(
    steps: tuple[_Step, ...], statement: WriteCall
) -> None:
    port = ScriptedAdapter(Transact(Read(rows=[_row()]), Write(), Read(rows=[])))
    spent: list[BaseException] = []

    def fn(tx: TxnContext) -> None:
        source = tx.find(mm.Account.where(mm.Account.id == 1)).result()
        for step in steps:
            step(tx, source)
        tx.find(mm.Account.where(mm.Account.id == 2))
        with pytest.raises(WriteEvidenceError) as refused:
            tx.amend(source.edit(owner="Again"))
        spent.append(refused.value)

    account_db(port).transact(fn)
    assert _calls(port)[1] == statement
    assert cast("WriteEvidenceError", spent[0]).code == "write-evidence-consumed"


def test_a_composed_write_whose_gate_fails_reports_the_callers_precondition() -> None:
    port = ScriptedAdapter(Transact(Read(rows=[_row()]), Write(affected=0)))

    def fn(tx: TxnContext) -> None:
        source = tx.find(mm.Account.where(mm.Account.id == 1)).result()
        tx.amend(source.edit(owner="Bo"))
        _patch(tx, balance="150.00")

    with raises_contextualized(WritePreconditionError):
        account_db(port).transact(fn)


@pytest.mark.parametrize(
    ("first", "second"),
    [(_d, _p), (_d, _r), (_x, _p), (_x, _r), (_x, _o)],
    ids=["D-P", "D-R", "X-P", "X-R", "X-O"],
)
def test_a_write_assigning_after_a_destruction_of_its_state_is_refused(
    first: _Step, second: _Step
) -> None:
    port = ScriptedAdapter(Transact(Read(rows=[_row()]), Write()))

    def fn(tx: TxnContext) -> None:
        source = tx.find(mm.Account.where(mm.Account.id == 1)).result()
        first(tx, source)
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

    def fn(tx: TxnContext) -> None:
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

    def fn(tx: TxnContext) -> None:
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


# --------------------------------------------------------------------------- #
# An object this attempt inserted is written through its source until commit. #
# --------------------------------------------------------------------------- #
@_REPRESENTATIONS
@pytest.mark.parametrize("flushed", [False, True], ids=["pending", "after-a-helper-read"])
def test_a_target_write_of_an_object_this_attempt_inserted_is_refused(
    representation: _Representation, flushed: bool
) -> None:
    port = ScriptedAdapter(Transact(Write(), Read(rows=[]), Write()))

    def fn(tx: TxnContext) -> None:
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
        tx.wire.amend_if("Account", {"id": 1}, version=1)
        tx.amend(inserted.edit(balance=Decimal("2.00")))

    account_db(port).transact(fn)
    assert [type(call) for call in _calls(port)] == (
        [WriteCall, ReadCall, WriteCall] if flushed else [WriteCall]
    )


@_REPRESENTATIONS
def test_a_deletion_of_an_object_this_attempt_inserted_is_refused(
    representation: _Representation,
) -> None:
    port = ScriptedAdapter(Transact(Write()))

    def fn(tx: TxnContext) -> None:
        tx.insert(mm.Account(id=1, owner="Ada", balance=Decimal("1.00")))
        with pytest.raises(WriteEvidenceError) as refused:
            _delete(tx, representation, version=1)
        assert refused.value.code == "write-evidence-inserted"

    account_db(port).transact(fn)
    assert [type(call) for call in _calls(port)] == [WriteCall]


def test_a_cancelled_insertion_of_an_object_still_refuses_a_target_write_of_it() -> None:
    port = ScriptedAdapter(Transact())

    def fn(tx: TxnContext) -> None:
        inserted = mm.Account(id=1, owner="Ada", balance=Decimal("1.00"))
        tx.insert(inserted)
        tx.delete(inserted)
        with pytest.raises(WriteEvidenceError, match="inserted the object"):
            _patch(tx, version=1, balance="2.00")

    account_db(port).transact(fn)
    assert _calls(port) == []


def test_a_committed_object_rewritten_in_this_attempt_is_target_writable() -> None:
    port = ScriptedAdapter(Transact(Read(rows=[_row()]), Write(), Read(rows=[_row(4)]), Write()))

    def fn(tx: TxnContext) -> None:
        source = tx.find(mm.Account.where(mm.Account.id == 1)).result()
        tx.amend(source.edit(owner="Bo"))
        assert tx.find(mm.Account.where(mm.Account.id == 1)).result().version == 4
        _patch(tx, version=4, balance="150.00")

    account_db(port).transact(fn)
    assert _calls(port)[-1] == WriteCall(_GATED_BALANCE, (Decimal("150.00"), 5, 1, 4))


# --------------------------------------------------------------------------- #
# The two update overloads, addressing, subtypes, and keyword-only arguments. #
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("verb", ["amend", "replace"])
@pytest.mark.parametrize("keyword", ["version", "tx_start", "valid_from"])
def test_a_source_write_takes_no_condition_or_start(verb: str, keyword: str) -> None:
    port = ScriptedAdapter(Transact(Read(rows=[_row()])))
    stated: dict[str, object] = {"version": 3, "tx_start": FIXED, "valid_from": FIXED}

    def fn(tx: TxnContext) -> None:
        node = tx.wire.find(_ACCOUNT_ONE).result()
        write = cast("Callable[..., None]", getattr(tx.wire, verb))
        with pytest.raises(TypeError, match=keyword):
            write(node, {"balance": "1.00"}, **{keyword: stated[keyword]})
        typed = cast("Callable[..., None]", getattr(tx, verb))
        with pytest.raises(TypeError, match=keyword):
            typed(
                mm.Account(id=1, owner="Ada", balance=Decimal("1.00")), **{keyword: stated[keyword]}
            )

    account_db(port).transact(fn)


def test_a_typed_replacement_of_a_read_value_is_addressed_by_its_key_alone() -> None:
    port = ScriptedAdapter(Transact(Read(rows=[_row()]), Write()))

    def fn(tx: TxnContext) -> None:
        fetched = tx.find(mm.Account.where(mm.Account.id == 1)).result()
        tx.replace_if(fetched.edit(owner="Bo"), version=7)

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

    def fn(tx: TxnContext) -> None:
        fetched = tx.find(ledger.where(ledger.id == 1)).result()
        tx.replace_if(fetched.edit(note="changed"), version=3)

    db_for(DomainModel(entity), port).transact(fn)
    write = _calls(port)[-1]
    assert write == WriteCall(
        POSTGRES.to_driver_sql(
            "update ledger set note = ?, version = ? where id = ? and version = ?"
        ),
        ("changed", 4, 1, 3),
    )


@pytest.mark.parametrize("concurrency", ["optimistic", "locking"])
def test_a_subtype_target_write_is_guarded_by_its_tag_and_refuses_a_sibling_member(
    concurrency: Literal["optimistic", "locking"],
) -> None:
    stored = {"id": 4, "name": "Skua", "berths": 6, "version": 3}
    acquired = [Read(rows=[stored])] if concurrency == "locking" else []
    port = ScriptedAdapter(Transact(*acquired, Write()))

    def fn(tx: TxnContext) -> None:
        with pytest.raises(WriteRejectedError):
            tx.wire.amend_if("Ferry", {"id": 4, "pull": 1}, version=3)
        tx.wire.amend_if("Ferry", {"id": 4, "berths": 8}, version=3)

    db_for(VESSEL, port).transact(fn, concurrency=concurrency)
    *reads, write = _calls(port)
    assert all(
        isinstance(read, ReadCall) and "kind" in read.sql and "for share" in read.sql
        for read in reads
    )
    assert isinstance(write, WriteCall)
    guard = "where id = %s and kind = %s" + (" and version = %s" if not reads else "")
    assert write.sql.endswith(guard)
    assert write.binds == ((8, 4, 4, "ferry", 3) if not reads else (8, 4, 4, "ferry"))


_KEYWORDS: dict[str, tuple[str, ...]] = {
    "amend_if": ("valid_from", "until", "version", "tx_start"),
    "replace_if": ("valid_from", "until", "version", "tx_start"),
    "delete_if": ("version", "tx_start"),
    "terminate_if": ("valid_from", "until", "version", "tx_start"),
}


@pytest.mark.parametrize("owner", [TxnContext, WireTransactionView], ids=["typed", "wire"])
@pytest.mark.parametrize("name", list(_KEYWORDS))
def test_a_target_writes_condition_and_bounds_are_keyword_only(
    owner: type[object], name: str
) -> None:
    parameters = inspect.signature(getattr(owner, name)).parameters
    for keyword in _KEYWORDS[name]:
        assert parameters[keyword].kind is inspect.Parameter.KEYWORD_ONLY
        assert parameters[keyword].default is OMITTED
