"""Temporal writes that leave a milestone as it was, through the public verbs
(scripted port)."""

from __future__ import annotations

import dataclasses
import datetime as dt
from decimal import Decimal
from typing import Literal

import pytest

from parallax.core.internal.dialect import POSTGRES
from parallax.snapshot import TxnContext
from tests._support import mirrored_models as mm
from tests._support.db_port import Read, ScriptedAdapter, Transact, Write, WriteCall
from tests.unit._transact_support import BALANCE, balance_row, db_for

type _Representation = Literal["typed", "wire"]

_REPRESENTATIONS = pytest.mark.parametrize("representation", ["typed", "wire"])
_T0 = dt.datetime(2023, 12, 1, tzinfo=dt.UTC)
_UNCOUNTED = dataclasses.replace(POSTGRES, counts_unchanged_rows=False)


def _writes(port: ScriptedAdapter) -> list[WriteCall]:
    return [call for call in port.calls if isinstance(call, WriteCall)]


def _restate(tx: TxnContext, representation: _Representation, value: str = "5.00") -> None:
    if representation == "typed":
        fetched = tx.find(mm.Balance.where(mm.Balance.id == 1)).result()
        tx.amend(fetched.edit(value=Decimal(value)))
        return
    node = tx.wire.find(
        {
            "target": "parallax.compatibility.Balance",
            "predicate": {"eq": {"path": "parallax.compatibility.Balance.id", "value": 1}},
            "temporal": {"transaction-time": {"asOf": "latest"}},
        }
    ).result()
    tx.wire.amend(node, {"value": value})


@_REPRESENTATIONS
def test_where_the_count_proves_no_guard_an_unchanged_row_is_closed_and_chained(
    representation: _Representation,
) -> None:
    port = ScriptedAdapter(
        Transact(Read(rows=[balance_row(in_z=_T0)]), Write(times=2)), dialect=_UNCOUNTED
    )
    db_for(BALANCE, port).transact(lambda tx: _restate(tx, representation))
    close, chained = _writes(port)
    assert close.sql.startswith("update px.balance set out_z = ?")
    assert chained.sql.startswith("insert into px.balance")
