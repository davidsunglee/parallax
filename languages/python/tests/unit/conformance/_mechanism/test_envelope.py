"""The conformance engine's observation envelope: each statement a lane reports,
as the emission a case grades.

Docker-free. A run reports the very Lowered Statement each Database Call
borrowed, so an emission's binds are that statement's compiler-owned canonical
Wire projection rather than the carrier the driver was handed.
"""

from __future__ import annotations

import datetime as dt
import decimal

import pytest

from parallax.conformance._mechanism import envelope
from parallax.conformance._mechanism.envelope import Emission
from parallax.core.base import STRING, NeutralType
from parallax.core.base import Decimal as DecimalType
from parallax.core.sql_gen import LoweredStatement, SqlGenError
from parallax.core.sql_gen._context import (
    _TypedBindSpan,  # pyright: ignore[reportPrivateUsage] - unit test builds sql_gen's private bind records directly
)

_UPDATE = "update account set balance = ?"


def _balance(value: object, declared: NeutralType | None = None) -> LoweredStatement:
    bind_type = DecimalType(8, 2) if declared is None else declared
    return LoweredStatement(_UPDATE, (value,), (_TypedBindSpan(0, 1, bind_type, "MANAGED"),))


def test_a_delivered_statement_is_reported_through_its_wire_projection() -> None:
    delivered = _balance(decimal.Decimal("250.00"))
    assert Emission("/scenario/1/write", delivered).to_json() == {
        "casePointer": "/scenario/1/write",
        "sql": _UPDATE,
        "binds": ["250.00"],
    }


def test_the_projection_follows_the_statements_own_type_metadata() -> None:
    # The metadata the compiler attached decides the Wire spelling, so a
    # statement declaring a different type reports what it declares: a golden
    # grading the emission sees the delivered type, never a reconstruction.
    assert Emission("/write", _balance("251.00", STRING)).to_json()["binds"] == ["251.00"]
    assert Emission("/write", _balance(decimal.Decimal("251.0"))).to_json()["binds"] == ["251.00"]


def test_emissions_keep_each_steps_statements_in_order_under_its_pointer() -> None:
    first, second, third = (_balance(decimal.Decimal(value)) for value in ("1", "2", "3"))
    reported = envelope.emissions(
        [
            ("/scenario/0/write", (first, second)),
            ("/scenario/1/objectQuery", ()),
            ("/scenario/2/write", (third,)),
        ]
    )
    assert [(emission.case_pointer, emission.statement) for emission in reported] == [
        ("/scenario/0/write", first),
        ("/scenario/0/write", second),
        ("/scenario/2/write", third),
    ]


def test_an_unannotated_non_wire_carrier_cannot_be_reported() -> None:
    statement = LoweredStatement("insert into shift(span) values (?)", (dt.timedelta(hours=1),))
    with pytest.raises(SqlGenError, match="is not an ordinary Wire value"):
        Emission("/write", statement).to_json()
