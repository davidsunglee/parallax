"""Write-DML lowering unit tests (the composition seam, m-sql write DML).

`parallax.snapshot.handle.lower_write` is the single write-lowering function both
the developer transaction path and the conformance engine reuse. These tests pin
its byte-exact non-temporal keyed emissions against the corpus goldens
(`m-unit-work-001/003/005/006`), compose it with the M3 planner for the coalescing
/ mixed-flush / cancellation cases (`-008/-009/-010`), and assert every not-yet-
lowered form (temporal, optimistic-gated, predicate-selected, inheritance,
milestone verbs) is refused with a loud ``WriteLoweringError`` — never a wrong
emission — mirroring the read compiler's forward-error posture.
"""

from __future__ import annotations

import pytest

from parallax.conformance import models
from parallax.core import op_algebra as oa
from parallax.core.db_port import JsonDocument
from parallax.core.descriptor import Metamodel
from parallax.core.dialect import POSTGRES, Dialect
from parallax.core.sql_gen import Statement
from parallax.core.unit_work import (
    KeyedWrite,
    Observation,
    PlannedWrite,
    PredicateWrite,
    WriteInstruction,
    WriteTarget,
    plan_flush,
)
from parallax.snapshot.handle import WriteLoweringError, lower_write

pytestmark = pytest.mark.unit

_MODELS = models.load_models()
ACCOUNT = _MODELS["account"]
ORDERS = _MODELS["orders"]
CUSTOMER = _MODELS["customer"]
BALANCE = _MODELS["balance"]
PAYMENT = _MODELS["payment"]

_B1 = "2024-01-01T00:00:00+00:00"


def _lower(
    instruction: WriteInstruction,
    meta: Metamodel,
    *,
    observation: Observation | None = None,
    dialect: Dialect = POSTGRES,
) -> list[Statement]:
    return lower_write(
        PlannedWrite(instruction=instruction, observation=observation), meta, dialect
    )


def _flush_and_lower(buffer: list[WriteInstruction], meta: Metamodel) -> list[Statement]:
    plan = plan_flush(buffer, {}, None, meta)
    return [stmt for planned in plan.writes for stmt in lower_write(planned, meta, POSTGRES)]


# --------------------------------------------------------------------------- #
# Non-temporal keyed lowering — byte-exact against the corpus goldens.         #
# --------------------------------------------------------------------------- #
def test_insert_projects_every_present_column_in_column_order() -> None:
    # m-unit-work-001 step 0.
    statement = _lower(
        KeyedWrite(
            "insert", "Account", ({"id": 7, "owner": "Newton", "balance": 5.00, "version": 1},)
        ),
        ACCOUNT,
    )[0]
    assert statement.sql == "insert into account(id, owner, balance, version) values (?, ?, ?, ?)"
    assert statement.binds == (7, "Newton", 5.00, 1)


def test_insert_omits_an_absent_nullable_column() -> None:
    # m-unit-work-003 step 1: OrderItem's nullable shipped_on is absent from the write
    # input, so the INSERT is narrower (4 of 5 columns) — never an explicit NULL bind.
    statement = _lower(
        KeyedWrite(
            "insert", "OrderItem", ({"id": 200, "orderId": 100, "sku": "X-1", "quantity": 3},)
        ),
        ORDERS,
    )[0]
    assert (
        statement.sql == "insert into order_item(id, order_id, sku, quantity) values (?, ?, ?, ?)"
    )
    assert statement.binds == (200, 100, "X-1", 3)


def test_insert_orders_columns_by_column_order_not_row_order() -> None:
    # m-unit-work-003 step 0: the row is authored id..orderedOn; the emission follows
    # descriptor columnOrder (orderedOn -> ordered_on last among Order's scalars).
    row = {
        "orderedOn": "2024-07-01",
        "id": 100,
        "name": "Hopper",
        "sku": "X-1",
        "qty": 1,
        "price": 9.99,
        "active": True,
    }
    statement = _lower(KeyedWrite("insert", "Order", (row,)), ORDERS)[0]
    assert statement.sql == (
        "insert into orders(id, name, sku, qty, price, active, ordered_on) "
        "values (?, ?, ?, ?, ?, ?, ?)"
    )
    assert statement.binds == (100, "Hopper", "X-1", 1, 9.99, True, "2024-07-01")


def test_update_sets_non_pk_columns_in_column_order_keyed_by_pk() -> None:
    # m-unit-work-005 step 0 (version carried as plain data — no opt-lock advance in M4).
    statement = _lower(
        KeyedWrite("update", "Account", ({"id": 1, "balance": 175.00, "version": 2},)), ACCOUNT
    )[0]
    assert statement.sql == "update account set balance = ?, version = ? where id = ?"
    assert statement.binds == (175.00, 2, 1)


def test_delete_is_keyed_by_the_primary_key() -> None:
    # m-unit-work-006 step 0.
    statement = _lower(KeyedWrite("delete", "Account", ({"id": 3},)), ACCOUNT)[0]
    assert statement.sql == "delete from account where id = ?"
    assert statement.binds == (3,)


def test_value_object_document_binds_as_one_json_document_in_column_order() -> None:
    # A value-object member rides its columnOrder position as one JsonDocument — the
    # whole document, never decomposed (m-sql valueObject atomic document write).
    statement = _lower(
        KeyedWrite("insert", "Customer", ({"id": 1, "name": "Ada", "address": {"city": "Oslo"}},)),
        CUSTOMER,
    )[0]
    assert statement.sql == "insert into customer(id, name, address) values (?, ?, ?)"
    assert statement.binds[:2] == (1, "Ada")
    assert statement.binds[2] == JsonDocument({"city": "Oslo"})


# --------------------------------------------------------------------------- #
# Composed with the planner — coalescing / mixed flush / cancellation.         #
# --------------------------------------------------------------------------- #
def test_insert_then_update_coalesces_to_one_final_value_insert() -> None:
    # m-unit-work-008: buffered insert + update of the same new object -> ONE insert.
    statements = _flush_and_lower(
        [
            KeyedWrite(
                "insert", "Account", ({"id": 8, "owner": "Turing", "balance": 1.00, "version": 1},)
            ),
            KeyedWrite("update", "Account", ({"id": 8, "balance": 99.00},)),
        ],
        ACCOUNT,
    )
    assert len(statements) == 1
    assert (
        statements[0].sql == "insert into account(id, owner, balance, version) values (?, ?, ?, ?)"
    )
    assert statements[0].binds == (8, "Turing", 99.00, 1)


def test_mixed_flush_lowers_insert_then_update_then_delete_in_order() -> None:
    # m-unit-work-009: three objects, one flush, canonical combined order.
    statements = _flush_and_lower(
        [
            KeyedWrite(
                "insert", "Account", ({"id": 9, "owner": "Noether", "balance": 5.00, "version": 1},)
            ),
            KeyedWrite("update", "Account", ({"id": 1, "balance": 20.00, "version": 2},)),
            KeyedWrite("delete", "Account", ({"id": 3},)),
        ],
        ACCOUNT,
    )
    assert [(s.sql, s.binds) for s in statements] == [
        (
            "insert into account(id, owner, balance, version) values (?, ?, ?, ?)",
            (9, "Noether", 5.00, 1),
        ),
        ("update account set balance = ?, version = ? where id = ?", (20.00, 2, 1)),
        ("delete from account where id = ?", (3,)),
    ]


def test_insert_then_delete_cancels_to_no_dml() -> None:
    # m-unit-work-010: the cancelled flush emits nothing.
    statements = _flush_and_lower(
        [
            KeyedWrite("insert", "Account", ({"id": 9, "owner": "Noether", "balance": 5.00},)),
            KeyedWrite("delete", "Account", ({"id": 9},)),
        ],
        ACCOUNT,
    )
    assert statements == []


# --------------------------------------------------------------------------- #
# Forward-error posture — every not-yet-lowered form refused loudly.           #
# --------------------------------------------------------------------------- #
def test_predicate_selected_write_is_refused() -> None:
    predicate = PredicateWrite("delete", WriteTarget("Account", oa.All()))
    with pytest.raises(WriteLoweringError, match="predicate-selected"):
        _lower(predicate, ACCOUNT)


def test_optimistic_gated_write_is_refused() -> None:
    update = KeyedWrite("update", "Account", ({"id": 1, "balance": 0.00},))
    with pytest.raises(WriteLoweringError, match="optimistic-lock"):
        _lower(update, ACCOUNT, observation=Observation(version=3))


def test_temporal_entity_write_is_refused() -> None:
    insert = KeyedWrite("insert", "Balance", ({"id": 9, "acctNum": "D", "value": 100.00},))
    with pytest.raises(WriteLoweringError, match="temporal write"):
        _lower(insert, BALANCE)


def test_inheritance_family_write_is_refused() -> None:
    # A concrete-subtype write (tag / concrete-subtype DML) is deferred past the M4 keyed
    # non-temporal path — the forward-error names m-inheritance / Phase 8.
    insert = KeyedWrite("insert", "CardPayment", ({"id": 1},))
    with pytest.raises(WriteLoweringError, match="inheritance-family"):
        _lower(insert, PAYMENT)


def test_milestone_verb_on_a_non_temporal_entity_is_refused() -> None:
    with pytest.raises(WriteLoweringError, match="temporal milestone verb"):
        _lower(KeyedWrite("terminate", "Account", ({"id": 1},)), ACCOUNT)


def test_business_bound_on_a_non_temporal_entity_is_refused() -> None:
    insert = KeyedWrite("insert", "Account", ({"id": 1, "balance": 1.00},), business_from=_B1)
    with pytest.raises(WriteLoweringError, match="business bound"):
        _lower(insert, ACCOUNT)
