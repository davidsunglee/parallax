"""Materializing predicate writes driven through the real verbs over a fake port
(`m-unit-work`): what a temporal group lowers to per selected row, and the rows
its no-op elimination keeps out of the buffer."""

from __future__ import annotations

import datetime as dt
from decimal import Decimal

from parallax.conformance.scripted_clock import FixedClock
from parallax.core.base import INFINITY
from parallax.snapshot import Database, Transaction
from tests._support import mirrored_models as mm
from tests._support.db_port import (
    Read,
    ScriptedAdapter,
    Transact,
    Write,
    WriteCall,
)
from tests._support.root_ownership import own_root
from tests.unit._transact_support import BALANCE as BALANCE_MODEL
from tests.unit._transact_support import (
    db_for,
)
from tests.unit._where_position_model import (
    WHERE_POSITION_META,
    WherePosition,
)


# --------------------------------------------------------------------------- #
# End to end: structural sharing survives materialization, temporal          #
# expansion, and lowering together, for a multi-row bitemporal resolve.       #
# --------------------------------------------------------------------------- #
def _position_row(row_id: int) -> dict[str, object]:
    return {
        "id": row_id,
        "acct_num": "A",
        "value": Decimal("200.00"),
        "from_z": dt.datetime(2024, 1, 1, tzinfo=dt.UTC),
        "thru_z": INFINITY,
        "in_z": dt.datetime(2024, 1, 1, tzinfo=dt.UTC),
        "out_z": INFINITY,
    }


def test_a_multi_row_materialized_bitemporal_update_lowers_one_close_and_chain_per_row() -> None:
    port = ScriptedAdapter(
        Transact(Read(rows=[_position_row(1), _position_row(2), _position_row(3)]), Write(times=9))
    )
    valid_from = dt.datetime(2024, 7, 1, tzinfo=dt.UTC)
    clock = FixedClock(dt.datetime(2024, 6, 1, tzinfo=dt.UTC))

    def fn(tx: Transaction) -> None:
        tx.amend_where(
            WherePosition.where(WherePosition.value == Decimal("200.00")),
            WherePosition.value.set(Decimal("300.00")),
            valid_from=valid_from,
        )

    own_root(
        Database.connect(port, WHERE_POSITION_META, clock=clock)
    ).using_database_login().transact(fn, concurrency="optimistic")
    writes = [(op.sql, op.binds) for op in port.calls if isinstance(op, WriteCall)]
    # Each resolved row settles to its own close + head + tail (three
    # statements), and the three rows' own topologies never interleave or
    # merge — the SAME per-row shape a single-row materialize proves,
    # scaled to three, with no shared mutable state between rows.
    assert len(writes) == 9
    closes = [(sql, binds) for sql, binds in writes if sql.startswith("update ")]
    inserts = [(sql, binds) for sql, binds in writes if sql.startswith("insert ")]
    assert len(closes) == 3
    assert len(inserts) == 6
    closed_keys = {binds[1] for _sql, binds in closes}  # `... where pos_id = ? and ...`
    inserted_keys = {binds[0] for _sql, binds in inserts}  # `insert into position(pos_id, ...`
    assert closed_keys == {1, 2, 3}
    assert inserted_keys == {1, 2, 3}


# --------------------------------------------------------------------------- #
# Streaming no-op elimination applies uniformly to the temporal (Predecessor  #
# Columns) branch, not only the versioned one — the per-row equality filter   #
# never retains a comparison-only column for either shape.                    #
# --------------------------------------------------------------------------- #
def _balance_row(row_id: int, value: Decimal) -> dict[str, object]:
    return {
        "bal_id": row_id,
        "acct_num": "A",
        "val": value,
        "in_z": dt.datetime(2024, 1, 1, tzinfo=dt.UTC),
        "out_z": INFINITY,
    }


def test_a_temporal_materializing_update_eliminates_a_no_op_row_and_chains_the_rest() -> None:
    port = ScriptedAdapter(
        Transact(
            Read(rows=[_balance_row(1, Decimal("5.00")), _balance_row(2, Decimal("10.00"))]),
            Write(times=2),
        )
    )

    def fn(tx: Transaction) -> None:
        tx.amend_where(
            mm.Balance.where(mm.Balance.value < Decimal("1000000.00")),
            mm.Balance.value.set(Decimal("5.00")),
        )

    db_for(BALANCE_MODEL, port).transact(fn, concurrency="optimistic")
    writes = [op for op in port.calls if isinstance(op, WriteCall)]
    # Row 1 already holds the assigned value and is streamed out before it
    # ever reaches a column builder; only row 2's close + chain reach the
    # driver.
    assert len(writes) == 2


def test_a_temporal_materializing_update_with_every_row_a_no_op_buffers_nothing() -> None:
    port = ScriptedAdapter(Transact(Read(rows=[_balance_row(1, Decimal("5.00"))])))

    def fn(tx: Transaction) -> None:
        tx.amend_where(
            mm.Balance.where(mm.Balance.value < Decimal("1000000.00")),
            mm.Balance.value.set(Decimal("5.00")),
        )

    db_for(BALANCE_MODEL, port).transact(fn, concurrency="optimistic")
    assert not any(isinstance(op, WriteCall) for op in port.calls)
