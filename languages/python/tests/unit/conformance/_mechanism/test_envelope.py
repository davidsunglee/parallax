"""The conformance engine's observation envelope: the reconciliation of a
write lane's planned statements with the DML the lifecycle delivered.

Docker-free. A write lane reports its plan, so the plan is admitted only where
the lifecycle confirms it is what ran — statement by statement, bind by bind,
through each statement's canonical Wire projection.
"""

from __future__ import annotations

import datetime as dt
import decimal
import uuid
from typing import Any, cast

import pytest

from parallax.conformance._mechanism import envelope
from parallax.conformance._mechanism.envelope import Emission, EngineError
from parallax.core.base import INFINITY, STRING
from parallax.core.base import Decimal as DecimalType
from parallax.core.db_port import JsonDocument
from parallax.core.sql_gen import LoweredStatement, SqlGenError
from parallax.core.sql_gen._context import (
    _TypedBindSpan,  # pyright: ignore[reportPrivateUsage]
    _WireBindOverride,  # pyright: ignore[reportPrivateUsage]
)
from tests.unit.conformance._wire_value_support import wire_value


def _lowered(sql: str, *binds: object) -> LoweredStatement:
    overrides = tuple(
        _WireBindOverride(
            index,
            cast("Any", wire_value(bind.value if isinstance(bind, JsonDocument) else bind)),
        )
        for index, bind in enumerate(binds)
        if not isinstance(bind, dt.timedelta)
    )
    return LoweredStatement(sql, tuple(binds), _wire_bind_overrides=overrides)


def test_a_plan_the_lifecycle_confirms_is_reported_unchanged() -> None:
    """Compiler-owned Wire projections reconcile different driver carriers."""
    plan = (
        _lowered(
            "update account set balance = ?",
            decimal.Decimal("250.00"),
            "infinity",
            "2024-01-01",
        ),
    )
    delivered = (
        _lowered(
            "update account set balance = ?",
            decimal.Decimal("250.00"),
            INFINITY,
            dt.date(2024, 1, 1),
        ),
    )
    assert envelope.delivered(plan, delivered, "a unit") == plan


def test_delivery_reconciliation_uses_lowered_statement_type_and_form_metadata() -> None:
    decimal_type = DecimalType(8, 2)
    planned = LoweredStatement(
        "update account set balance = ?",
        ("250.00",),
        (_TypedBindSpan(0, 1, decimal_type, "COMPARISON_TEXT"),),
    )
    delivered = LoweredStatement(
        "update account set balance = ?",
        (decimal.Decimal("250.00"),),
        (_TypedBindSpan(0, 1, decimal_type, "MANAGED"),),
    )
    assert envelope.delivered((planned,), (delivered,), "a unit") == (planned,)
    assert Emission("/write", delivered).to_json()["binds"] == ["250.00"]

    wrongly_declared = LoweredStatement(
        delivered.sql,
        ("251.00",),
        (_TypedBindSpan(0, 1, STRING, "MANAGED"),),
    )
    with pytest.raises(EngineError, match="canonical Wire"):
        envelope.delivered((planned,), (wrongly_declared,), "a unit")


def test_a_plan_the_lifecycle_contradicts_is_refused() -> None:
    plan = (_lowered("update account set balance = ?", 250.00),)
    for delivered, expected in (
        ((), "the plan holds 1 statement"),
        ((_lowered("delete from account", 250.00),), "is planned as"),
        ((_lowered("update account set balance = ?", 999.00),), "is planned with binds"),
        ((_lowered("update account set balance = ?"),), "is planned with binds"),
        ((_lowered("update account set balance = ?", "infinity"),), "is planned with binds"),
        ((_lowered("update account set balance = ?", True),), "is planned with binds"),
    ):
        with pytest.raises(EngineError, match=expected):
            envelope.delivered(plan, delivered, "a unit")


def test_a_bind_that_is_no_number_reconciles_only_by_equality() -> None:
    """The Decimal fallback answers for numbers alone, so a document and a text
    bind that differ are differences rather than spellings."""
    for planned, delivered in (
        (JsonDocument({"a": 1}), JsonDocument({"a": 2})),
        ("Ling", "Ada"),
    ):
        with pytest.raises(EngineError, match="is planned with binds"):
            envelope.delivered(
                (_lowered("update account set owner = ?", planned),),
                (_lowered("update account set owner = ?", delivered),),
                "a unit",
            )


def test_a_numeric_looking_string_is_no_decimal_spelling() -> None:
    """The cross-type licence belongs to the DECIMAL carrier, not to the string.

    A string reaching the wire is a semantic value of its own — a byte buffer's
    hex, a UUID, a date — and one that happens to parse as a number is a
    delivered type the case never authored. Sanctioning it by parse alone would
    let a driver coercing an integer bind to text, or a buffer to the number its
    hex reads as, leave the golden green.
    """
    for planned, delivered in (
        (1, "1"),
        ("1", 1),
        (b"\x01\x02\x03\x04", 1020304),
        (uuid.UUID(int=12), 12),
        (JsonDocument({"total": 250.00}), JsonDocument({"total": "250.00"})),
        (JsonDocument({"totals": [1]}), JsonDocument({"totals": ["1"]})),
    ):
        with pytest.raises(EngineError, match="is planned with binds"):
            envelope.delivered(
                (_lowered("update account set balance = ?", planned),),
                (_lowered("update account set balance = ?", delivered),),
                "a unit",
            )


def test_a_document_bind_reconciles_by_content_rather_than_key_order() -> None:
    """A value-object document write binds the whole document, and a mapping's
    key order is no part of the value either side names."""
    plan = (_lowered("insert into voyage(payload) values (?)", JsonDocument({"a": 1, "b": 2})),)
    delivered = (
        _lowered("insert into voyage(payload) values (?)", JsonDocument({"b": 2, "a": 1})),
    )
    assert envelope.delivered(plan, delivered, "a unit") == plan


def test_a_bind_reconciles_only_against_its_own_json_type() -> None:
    """The carrier a decode produces changes the SPELLING of a value, never its
    JSON type, so a type difference is a difference the case must see.

    Python equality alone would not say so: ``True == 1`` and ``False == 0``
    hold, and a mapping compared with ``==`` carries that hole into every member
    of a value-object document. A production defect binding the number 1 where
    the plan holds ``true`` is exactly the drift this reconciliation exists to
    report.
    """
    for planned, delivered in (
        (True, 1),
        (1, True),
        (False, 0),
        (None, 0),
        (None, ""),
        (JsonDocument({"active": True}), JsonDocument({"active": 1})),
        (JsonDocument({"tags": [1, True]}), JsonDocument({"tags": [1, 1]})),
        (JsonDocument({"geo": {"lat": True}}), JsonDocument({"geo": {"lat": 1}})),
        (JsonDocument({"a": 1}), JsonDocument({"a": 1, "b": 2})),
        (JsonDocument({"tags": [1]}), JsonDocument({"tags": [1, 2]})),
    ):
        with pytest.raises(EngineError, match="is planned with binds"):
            envelope.delivered(
                (_lowered("update account set flag = ?", planned),),
                (_lowered("update account set flag = ?", delivered),),
                "a unit",
            )


def test_a_document_member_reconciles_through_the_statement_wire_projection() -> None:
    plan = (
        _lowered(
            "insert into voyage(payload, seal) values (?, ?)",
            JsonDocument({"totals": [decimal.Decimal("250.00"), {"fee": decimal.Decimal("1.5")}]}),
            b"\x01\x02",
        ),
    )
    delivered = (
        _lowered(
            "insert into voyage(payload, seal) values (?, ?)",
            JsonDocument({"totals": [decimal.Decimal("250.00"), {"fee": decimal.Decimal("1.5")}]}),
            b"\x01\x02",
        ),
    )
    assert envelope.delivered(plan, delivered, "a unit") == plan
    with pytest.raises(EngineError, match="is planned with binds"):
        envelope.delivered(
            (_lowered("insert into voyage(seal) values (?)", b"\x01\x02"),),
            (_lowered("insert into voyage(seal) values (?)", b"\x01\x03"),),
            "a unit",
        )


def test_an_unannotated_non_wire_carrier_cannot_be_reconciled() -> None:
    statement = _lowered("insert into shift(span) values (?)", dt.timedelta(hours=1))
    with pytest.raises(SqlGenError, match="is not an ordinary Wire value"):
        envelope.delivered((statement,), (statement,), "a unit")
