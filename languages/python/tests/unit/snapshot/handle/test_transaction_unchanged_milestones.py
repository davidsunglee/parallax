"""Temporal writes that leave a milestone as it was, through the public verbs
(scripted port)."""

from __future__ import annotations

import dataclasses
import datetime as dt
from decimal import Decimal
from typing import Literal

import pytest

from parallax.core.dialect import POSTGRES
from parallax.core.unit_work import OptimisticLockConflictError
from parallax.snapshot.handle import Transaction, WriteEvidenceError
from tests._support import mirrored_models as mm
from tests._support.adoption import raises_contextualized
from tests._support.db_port import Read, ScriptedAdapter, Transact, Write, WriteCall
from tests.unit._transact_support import (
    BALANCE,
    INFINITY_INSTANT,
    WHERE_POSITION_META,
    WherePosition,
    balance_row,
    db_for,
)

type _Representation = Literal["typed", "wire"]

_REPRESENTATIONS = pytest.mark.parametrize("representation", ["typed", "wire"])
_T0 = dt.datetime(2023, 12, 1, tzinfo=dt.UTC)
_JAN, _MAR, _APR, _MAY, _AUG, _OCT, _DEC = (
    dt.datetime(2024, month, 1, tzinfo=dt.UTC) for month in (1, 3, 4, 5, 8, 10, 12)
)
_GUARD = "update balance set in_z = in_z where bal_id = %s and out_z = %s and in_z = %s"
_UNCOUNTED = dataclasses.replace(POSTGRES, counts_unchanged_rows=False)


def _writes(port: ScriptedAdapter) -> list[WriteCall]:
    return [call for call in port.calls if isinstance(call, WriteCall)]


def _restate(tx: Transaction, representation: _Representation, value: str = "5.00") -> None:
    if representation == "typed":
        fetched = tx.find(mm.Balance.where(mm.Balance.id == 1)).result()
        tx.update(fetched.edit(value=Decimal(value)))
        return
    node = tx.wire.find(
        {
            "target": "parallax.compatibility.Balance",
            "predicate": {"eq": {"attr": "parallax.compatibility.Balance.id", "value": 1}},
            "temporal": {"transaction-time": {"asOf": "latest"}},
        }
    ).result()
    tx.wire.update(node, {"value": value})


# --------------------------------------------------------------------------- #
# One milestone.                                                               #
# --------------------------------------------------------------------------- #
@_REPRESENTATIONS
def test_an_optimistic_update_restating_its_row_writes_one_guard(
    representation: _Representation,
) -> None:
    port = ScriptedAdapter(Transact(Read(rows=[balance_row(in_z=_T0)]), Write()))
    db_for(BALANCE, port).transact(lambda tx: _restate(tx, representation))
    (guard,) = _writes(port)
    assert guard.sql == _GUARD
    assert guard.binds[0] == 1 and guard.binds[2] == _T0


@_REPRESENTATIONS
def test_under_locking_an_update_restating_its_row_writes_nothing(
    representation: _Representation,
) -> None:
    port = ScriptedAdapter(Transact(Read(rows=[balance_row(in_z=_T0)])))
    db_for(BALANCE, port).transact(lambda tx: _restate(tx, representation), concurrency="locking")
    assert _writes(port) == []


@_REPRESENTATIONS
def test_where_the_count_proves_no_guard_an_unchanged_row_is_closed_and_chained(
    representation: _Representation,
) -> None:
    port = ScriptedAdapter(
        Transact(Read(rows=[balance_row(in_z=_T0)]), Write(times=2)), dialect=_UNCOUNTED
    )
    db_for(BALANCE, port).transact(lambda tx: _restate(tx, representation))
    close, chained = _writes(port)
    assert close.sql.startswith("update balance set out_z = %s")
    assert chained.sql.startswith("insert into balance")


def test_a_guard_that_matches_nothing_is_the_milestones_conflict() -> None:
    port = ScriptedAdapter(Transact(Read(rows=[balance_row(in_z=_T0)]), Write(affected=0)))
    with raises_contextualized(OptimisticLockConflictError):
        db_for(BALANCE, port).transact(lambda tx: _restate(tx, "typed"))
    assert [call.sql for call in _writes(port)] == [_GUARD]


def test_a_retried_conflict_reads_the_row_again_and_its_guard_matches() -> None:
    port = ScriptedAdapter(
        Transact(Read(rows=[balance_row(in_z=_T0)]), Write(affected=0)),
        Transact(Read(rows=[balance_row(in_z=_T0)]), Write()),
    )
    db_for(BALANCE, port).transact(
        lambda tx: _restate(tx, "typed"), retry_optimistic_conflicts=True
    )
    assert [call.sql for call in _writes(port)] == [_GUARD, _GUARD]


def test_a_guarded_source_is_spent_and_a_fresh_read_writes_again() -> None:
    port = ScriptedAdapter(
        Transact(
            Read(rows=[balance_row(in_z=_T0)]),
            Write(),
            Read(rows=[balance_row(in_z=_T0)]),
            Write(),
        )
    )

    def fn(tx: Transaction) -> None:
        fetched = tx.find(mm.Balance.where(mm.Balance.id == 1)).result()
        tx.update(fetched.edit(value=Decimal("5.00")))
        fresh = tx.find(mm.Balance.where(mm.Balance.id == 1)).result()
        with pytest.raises(WriteEvidenceError) as spent:
            tx.update(fetched.edit(value=Decimal("5.00")))
        assert spent.value.code == "write-evidence-consumed"
        tx.update(fresh.edit(value=Decimal("5.00")))

    db_for(BALANCE, port).transact(fn)
    assert [call.sql for call in _writes(port)] == [_GUARD, _GUARD]


def test_a_wire_projection_of_a_guarded_source_shares_its_spent_evidence() -> None:
    port = ScriptedAdapter(
        Transact(Read(rows=[balance_row(in_z=_T0)]), Write(), Read(rows=[balance_row(in_z=_T0)]))
    )

    def fn(tx: Transaction) -> None:
        snapshot = tx.find(mm.Balance.where(mm.Balance.id == 1))
        projected = snapshot.wire().result()
        tx.update(snapshot.result().edit(value=Decimal("5.00")))
        tx.find(mm.Balance.where(mm.Balance.id == 1)).result()
        with pytest.raises(WriteEvidenceError) as spent:
            tx.wire.update(projected, {"value": "5.00"})
        assert spent.value.code == "write-evidence-consumed"

    db_for(BALANCE, port).transact(fn)
    assert [call.sql for call in _writes(port)] == [_GUARD]


# --------------------------------------------------------------------------- #
# A range over several rectangles: each is kept or rewritten on its own.       #
# --------------------------------------------------------------------------- #
def _rectangle(start: dt.datetime, end: object, value: str) -> dict[str, object]:
    return {
        "id": 1,
        "acct_num": "A",
        "value": Decimal(value),
        "from_z": start,
        "thru_z": end,
        "in_z": _T0,
        "out_z": INFINITY_INSTANT,
    }


_COVERAGE = [
    _rectangle(_JAN, _APR, "100.00"),
    _rectangle(_MAY, _AUG, "180.00"),
    _rectangle(_AUG, _DEC, "100.00"),
]


def _find(tx: Transaction, at: dt.datetime) -> WherePosition:
    return tx.find(WherePosition.where(WherePosition.id == 1).as_of(valid_time=at)).result()


def test_a_range_guards_its_unchanged_rectangles_where_it_would_have_closed_them() -> None:
    port = ScriptedAdapter(
        Transact(Read(rows=[_COVERAGE[0]]), Read(rows=_COVERAGE), Write(times=4))
    )

    def fn(tx: Transaction) -> None:
        tx.update(_find(tx, _MAR).edit(value=Decimal("100.00")), until=_OCT)

    db_for(WHERE_POSITION_META, port).transact(fn)
    guard_first, close, guard_last, opened = _writes(port)
    guard = (
        "update where_position set in_z = in_z where id = %s and thru_z = %s and out_z = %s "
        "and in_z = %s"
    )
    assert (guard_first.sql, guard_last.sql) == (guard, guard)
    assert (guard_first.binds[1], guard_last.binds[1]) == (_APR, _DEC)
    assert close.sql.startswith("update where_position set out_z = %s")
    assert close.binds[2] == _AUG
    assert opened.sql.startswith("insert into where_position")
    assert Decimal("100.00") in opened.binds and _MAY in opened.binds


@pytest.mark.parametrize(
    ("value", "kept"), [("100.00", True), ("120.00", False)], ids=["kept", "rewritten"]
)
def test_a_read_of_a_rectangle_the_range_kept_stays_writable(value: str, kept: bool) -> None:
    # The range spends only its own source. A rectangle it rewrote is a state
    # this attempt changed, so an earlier read of it is stale; one it kept is not.
    port = ScriptedAdapter(
        Transact(
            Read(rows=[_COVERAGE[0]]),
            Read(rows=[_COVERAGE[2]]),
            Read(rows=_COVERAGE),
            Write(times=4 if kept else 8),
            Read(rows=[]),
            *((Write(times=3),) if kept else ()),
        )
    )
    november = dt.datetime(2024, 11, 1, tzinfo=dt.UTC)

    def fn(tx: Transaction) -> None:
        source = _find(tx, _MAR)
        last = _find(tx, november)
        tx.update(source.edit(value=Decimal(value)), until=_OCT)
        tx.find(WherePosition.where(WherePosition.id == 2).as_of(valid_time=_MAR)).result_or_none()
        if kept:
            tx.update(last.edit(acct_num="B"), until=_DEC)
            return
        with pytest.raises(WriteEvidenceError) as stale:
            tx.update(last.edit(acct_num="B"), until=_DEC)
        assert stale.value.code == "write-evidence-consumed"

    db_for(WHERE_POSITION_META, port).transact(fn)
