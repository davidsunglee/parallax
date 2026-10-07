"""Which rectangle a Typed temporal write closes when its key holds several
current at one Transaction Time (`m-temporal-write`): the one the written value
was read from, through the real handles over a fake port."""

from __future__ import annotations

import datetime as dt
from decimal import Decimal

import pytest

from parallax.core.db_port import MappingRow
from parallax.core.dialect import POSTGRES
from parallax.core.unit_work import (
    Concurrency,
)
from parallax.snapshot import Transaction
from tests._support.db_port import (
    Read,
    ScriptedAdapter,
    Transact,
    Write,
    WriteCall,
)
from tests.unit._transact_support import (
    INFINITY_INSTANT,
    db_for,
)
from tests.unit._where_position_model import (
    WHERE_POSITION_META,
    WherePosition,
)

# The two rectangles one key holds current at one Transaction Time, as the
# driver hands each back: real `datetime` values on both axes, the open-bound
# sentinel for an open one. They share nothing a close addresses or gates on — distinct
# Valid-Time windows and distinct `in_z` — so every bind below names exactly one
# of them.
_CURRENT_RECTANGLE: MappingRow = {
    "id": 1,
    "acct_num": "A",
    "value": Decimal("100.00"),
    "from_z": dt.datetime(2024, 4, 1, tzinfo=dt.UTC),
    "thru_z": INFINITY_INSTANT,
    "in_z": dt.datetime(2024, 2, 1, tzinfo=dt.UTC),
    "out_z": INFINITY_INSTANT,
}

_RETROACTIVE_RECTANGLE: MappingRow = {
    "id": 1,
    "acct_num": "A",
    "value": Decimal("50.00"),
    "from_z": dt.datetime(2024, 1, 1, tzinfo=dt.UTC),
    "thru_z": dt.datetime(2024, 4, 1, tzinfo=dt.UTC),
    "in_z": dt.datetime(2024, 1, 1, tzinfo=dt.UTC),
    "out_z": INFINITY_INSTANT,
}


@pytest.mark.parametrize(
    ("concurrency", "gate_sql", "gate_binds"),
    [
        ("locking", "", ()),
        ("optimistic", " and in_z = ?", (dt.datetime(2024, 2, 1, tzinfo=dt.UTC),)),
    ],
    ids=["locking", "optimistic"],
)
def test_a_close_addresses_the_rectangle_the_written_value_came_from(
    concurrency: Concurrency, gate_sql: str, gate_binds: tuple[dt.datetime, ...]
) -> None:
    # One key holding TWO rectangles current at one Transaction Time — what a
    # retroactive correction leaves behind — read twice in one transaction: once
    # at the correction's own instant, then once at a Valid-Time instant inside the
    # earlier rectangle, then updated from the value the FIRST read handed back.
    # The close must address the rectangle THAT value came from: `thru_z` binds its own exclusive
    # Valid-Time end, head and tail reconstruct its own window split at the
    # correction, and the optimistic gate binds its own `in_z`. The distinction is
    # which read a write settles against — an as-of read is evidence about the
    # milestone IT observed, never about whichever milestone the same primary key
    # happened to be read at last, so reading one row at a second coordinate
    # leaves the first read's evidence intact. Driven through the developer verbs
    # rather than a hand-supplied observation because the misresolution is in how
    # the observation is resolved, which a lowering-only probe cannot see.
    port = ScriptedAdapter(
        Transact(
            Read(rows=[_CURRENT_RECTANGLE]), Read(rows=[_RETROACTIVE_RECTANGLE]), Write(times=3)
        )
    )

    def fn(tx: Transaction) -> None:
        current = tx.find(
            WherePosition.where(WherePosition.id == 1).as_of(
                valid_time=dt.datetime(2024, 8, 1, tzinfo=dt.UTC)
            )
        ).result()
        tx.find(
            WherePosition.where(WherePosition.id == 1).as_of(
                valid_time=dt.datetime(2024, 2, 15, tzinfo=dt.UTC)
            )
        ).result()
        tx.update(current.edit(value=Decimal("150.00")))

    db_for(WHERE_POSITION_META, port).transact(fn, concurrency=concurrency)

    close, head, tail = (op for op in port.calls if isinstance(op, WriteCall))
    assert close == WriteCall(
        POSTGRES.to_driver_sql(
            "update where_position set out_z = ? "
            f"where id = ? and thru_z = ? and out_z = ?{gate_sql}"
        ),
        (dt.datetime(2024, 6, 1, tzinfo=dt.UTC), 1, "infinity", "infinity", *gate_binds),
    )
    assert head.binds == (
        1,
        "A",
        Decimal("100.00"),
        dt.datetime(2024, 4, 1, tzinfo=dt.UTC),
        dt.datetime(2024, 8, 1, tzinfo=dt.UTC),
        dt.datetime(2024, 6, 1, tzinfo=dt.UTC),
        INFINITY_INSTANT,
    )
    assert tail.binds == (
        1,
        "A",
        Decimal("150.00"),
        dt.datetime(2024, 8, 1, tzinfo=dt.UTC),
        INFINITY_INSTANT,
        dt.datetime(2024, 6, 1, tzinfo=dt.UTC),
        INFINITY_INSTANT,
    )
