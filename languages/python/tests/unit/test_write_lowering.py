"""Write-DML lowering unit tests (the composition seam, m-sql write DML).

``parallax.snapshot.handle.lower_write`` is the single write-lowering function both
the developer transaction path and the conformance engine reuse. These tests pin
its byte-exact non-temporal keyed emissions against the corpus goldens
(``m-unit-work-001/003/005/006``, ``m-opt-lock-002/005/006/013``,
``m-inheritance-007/008/009/010/084/104``, ``m-pk-gen-001``), compose it with the
M3 planner for the coalescing / mixed-flush / cancellation cases
(``-008/-009/-010``), pin the ``m-opt-lock`` version gate/advance/conflict policy
(observation-required, gate-optimistic-only, delete's opportunistic bind, the
M4-era literal-version passthrough, the derived initial version), the inheritance
tag derivation/guard/opt-lock composition, and the pk-gen ``max``/``increment``
marker lowering — and assert every not-yet-lowered form (temporal, predicate-
selected, multi-row batch, an unrecognized marker) is refused with a loud
``WriteLoweringError`` — never a wrong emission — mirroring the read compiler's
forward-error posture.
"""

from __future__ import annotations

import pytest

from parallax.conformance import models
from parallax.core import op_algebra as oa
from parallax.core import opt_lock
from parallax.core.db_port import JsonDocument
from parallax.core.descriptor import Metamodel
from parallax.core.dialect import POSTGRES, Dialect
from parallax.core.sql_gen import Statement
from parallax.core.unit_work import (
    Concurrency,
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
RATE = _MODELS["rate"]
VEHICLE = _MODELS["vehicle"]
APPLIANCE = _MODELS["appliance"]
DOCUMENT = _MODELS["document"]
PK_MAX = _MODELS["pk-max"]
PK_SEQUENCE = _MODELS["pk-sequence"]

_B1 = "2024-01-01T00:00:00+00:00"


def _lower(
    instruction: WriteInstruction,
    meta: Metamodel,
    *,
    observation: Observation | None = None,
    dialect: Dialect = POSTGRES,
    concurrency: Concurrency = "locking",
) -> list[Statement]:
    return lower_write(
        PlannedWrite(instruction=instruction, observation=observation), meta, dialect, concurrency
    )


def _flush_and_lower(
    buffer: list[WriteInstruction], meta: Metamodel, *, concurrency: Concurrency = "locking"
) -> list[Statement]:
    plan = plan_flush(buffer, {}, None, meta)
    return [
        stmt
        for planned in plan.writes
        for stmt in lower_write(planned, meta, POSTGRES, concurrency)
    ]


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
    # m-unit-work-005 step 0 (version carried as plain data — the M4-era literal-
    # version passthrough this increment keeps byte-identical: no observation
    # consulted, no advance recomputed, no gate).
    statement = _lower(
        KeyedWrite("update", "Account", ({"id": 1, "balance": 175.00, "version": 2},)),
        ACCOUNT,
        concurrency="optimistic",
    )[0]
    assert statement.sql == "update account set balance = ?, version = ? where id = ?"
    assert statement.binds == (175.00, 2, 1)


def test_delete_is_keyed_by_the_primary_key() -> None:
    # m-unit-work-006 step 0 (no recorded observation — delete's opt-lock
    # participation is opportunistic, never a hard requirement; stays ungated).
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
# m-opt-lock: the version gate / advance / conflict policy.                    #
# --------------------------------------------------------------------------- #
def test_versioned_update_without_a_row_carried_version_requires_observation() -> None:
    update = KeyedWrite("update", "Account", ({"id": 1, "balance": 50.00},))
    with pytest.raises(opt_lock.UnobservedVersionError, match="prior transaction-scoped"):
        _lower(update, ACCOUNT)


def test_versioned_update_derives_the_advance_from_the_observation_locking_mode() -> None:
    # locking mode: version = observed + 1 in the SET, no gate.
    update = KeyedWrite("update", "Account", ({"id": 1, "balance": 50.00},))
    statement = _lower(update, ACCOUNT, observation=Observation(version=3), concurrency="locking")[
        0
    ]
    assert statement.sql == "update account set balance = ?, version = ? where id = ?"
    assert statement.binds == (50.00, 4, 1)


def test_versioned_update_gates_on_the_observed_version_optimistic_mode() -> None:
    # optimistic mode: SAME advance, plus `and version = ?` binding the observed
    # value LAST.
    update = KeyedWrite("update", "Account", ({"id": 1, "balance": 50.00},))
    statement = _lower(
        update, ACCOUNT, observation=Observation(version=3), concurrency="optimistic"
    )[0]
    assert (
        statement.sql == "update account set balance = ?, version = ? where id = ? and version = ?"
    )
    assert statement.binds == (50.00, 4, 1, 3)


def test_versioned_update_carrying_a_literal_version_is_never_observation_gated() -> None:
    # The M4-era plain-column-data shape (m-unit-work-005/009): an explicit
    # row-carried version key means no observation is consulted at all — no
    # requirement, no recomputed advance, no gate — even under optimistic mode.
    update = KeyedWrite("update", "Account", ({"id": 1, "balance": 175.00, "version": 2},))
    statement = _lower(update, ACCOUNT, concurrency="optimistic")[0]
    assert statement.sql == "update account set balance = ?, version = ? where id = ?"
    assert statement.binds == (175.00, 2, 1)


def test_versioned_delete_binds_the_observed_version_in_either_mode() -> None:
    # m-batch-write-004: DELETE binds the observed version whenever one is
    # recorded, unconditionally in EITHER mode (unlike UPDATE's optimistic-only
    # gate) — python.md §5's own asymmetric phrasing.
    delete = KeyedWrite("delete", "Account", ({"id": 3},))
    for concurrency in ("locking", "optimistic"):
        statement = _lower(
            delete, ACCOUNT, observation=Observation(version=1), concurrency=concurrency
        )[0]
        assert statement.sql == "delete from account where id = ? and version = ?"
        assert statement.binds == (3, 1)


def test_versioned_delete_without_an_observation_stays_ungated() -> None:
    # m-unit-work-006: an unobserved delete never raises — delete's opt-lock
    # participation is opportunistic, not a hard requirement (unlike UPDATE's).
    delete = KeyedWrite("delete", "Account", ({"id": 3},))
    statement = _lower(delete, ACCOUNT)[0]
    assert statement.sql == "delete from account where id = ?"
    assert statement.binds == (3,)


def test_versioned_insert_derives_the_initial_version_ignoring_any_row_carried_value() -> None:
    insert = KeyedWrite(
        "insert",
        "Account",
        ({"id": 9, "owner": "Noether", "balance": 5.00, "version": 99},),
    )
    statement = _lower(insert, ACCOUNT)[0]
    assert statement.sql == "insert into account(id, owner, balance, version) values (?, ?, ?, ?)"
    assert statement.binds == (9, "Noether", 5.00, opt_lock.INITIAL_VERSION)
    assert opt_lock.INITIAL_VERSION == 1


# --------------------------------------------------------------------------- #
# Inheritance-family keyed writes — tag derivation, tag guard, opt-lock        #
# composition (m-inheritance x m-sql x m-opt-lock).                            #
# --------------------------------------------------------------------------- #
def test_tph_insert_derives_the_tag_at_its_columnorder_position() -> None:
    # m-inheritance-007.
    insert = KeyedWrite(
        "insert", "CardPayment", ({"id": 10, "amount": 200.00, "cardNetwork": "Mastercard"},)
    )
    statement = _lower(insert, PAYMENT)[0]
    assert (
        statement.sql == "insert into payment(id, kind, amount, card_network) values (?, ?, ?, ?)"
    )
    assert statement.binds == (10, "card", 200.00, "Mastercard")


def test_tph_update_of_a_root_declared_attribute_is_tag_guarded() -> None:
    # m-inheritance-008.
    update = KeyedWrite("update", "CardPayment", ({"id": 1, "amount": 130.00},))
    statement = _lower(update, PAYMENT)[0]
    assert statement.sql == "update payment set amount = ? where id = ? and kind = ?"
    assert statement.binds == (130.00, 1, "card")


def test_tph_delete_is_tag_guarded() -> None:
    # m-inheritance-009.
    delete = KeyedWrite("delete", "CardPayment", ({"id": 2},))
    statement = _lower(delete, PAYMENT)[0]
    assert statement.sql == "delete from payment where id = ? and kind = ?"
    assert statement.binds == (2, "card")


def test_tpcs_insert_targets_the_concretes_own_table_no_tag() -> None:
    # m-inheritance-010.
    insert = KeyedWrite(
        "insert",
        "Invoice",
        ({"id": 10, "title": "Invoice-C", "currency": "USD", "amountDue": 300.00},),
    )
    statement = _lower(insert, DOCUMENT)[0]
    assert (
        statement.sql == "insert into invoice(id, title, currency, amount_due) values (?, ?, ?, ?)"
    )
    assert statement.binds == (10, "Invoice-C", "USD", 300.00)


def test_tpcs_delete_targets_the_concretes_own_table_no_tag() -> None:
    # m-inheritance-085.
    delete = KeyedWrite("delete", "Invoice", ({"id": 1},))
    statement = _lower(delete, DOCUMENT)[0]
    assert statement.sql == "delete from invoice where id = ?"
    assert statement.binds == (1,)


def test_tph_optlock_composition_tag_rides_identity_gate_binds_last() -> None:
    # m-inheritance-084: the resolved Q9 bind order end to end — pk, tag guard,
    # THEN the version gate (no inheritance exception to "the gate binds last").
    update = KeyedWrite("update", "Car", ({"id": 1, "name": "Coupe"},))
    statement = _lower(
        update, VEHICLE, observation=Observation(version=5), concurrency="optimistic"
    )[0]
    assert statement.sql == (
        "update vehicle set name = ?, version = ? where id = ? and kind = ? and version = ?"
    )
    assert statement.binds == ("Coupe", 6, 1, "car", 5)


def test_tpcs_optlock_composition_no_tag_guard_gate_binds_last() -> None:
    # m-inheritance-104: the TPCS analogue — no shared table, no tag, own table.
    update = KeyedWrite("update", "Fridge", ({"id": 1, "name": "Chill"},))
    statement = _lower(
        update, APPLIANCE, observation=Observation(version=5), concurrency="optimistic"
    )[0]
    assert statement.sql == "update fridge set name = ?, version = ? where id = ? and version = ?"
    assert statement.binds == ("Chill", 6, 1, 5)


# --------------------------------------------------------------------------- #
# pk-gen DB-computed markers — `max` (INSERT…SELECT fold) and `increment`      #
# (a self-referential registry advance).                                       #
# --------------------------------------------------------------------------- #
def test_pk_gen_max_folds_into_an_insert_select() -> None:
    # m-pk-gen-001.
    insert = KeyedWrite("insert", "Attendee", ({"id": {"computed": "maxPlusOne"}, "name": "Ada"},))
    statement = _lower(insert, PK_MAX)[0]
    assert statement.sql == (
        "insert into attendee(id, name) select coalesce(max(t0.id), ?) + ?, ? from attendee t0"
    )
    assert statement.binds == (0, 1, "Ada")


def test_pk_gen_increment_marker_self_references_the_column() -> None:
    update = KeyedWrite(
        "update", "PkSequence", ({"name": "badge_seq", "nextVal": {"increment": 1}},)
    )
    statement = _lower(update, PK_SEQUENCE)[0]
    assert statement.sql == "update pk_sequence set next_val = next_val + ? where name = ?"
    assert statement.binds == (1, "badge_seq")


def test_increment_marker_reaching_an_insert_is_refused() -> None:
    insert = KeyedWrite(
        "insert", "PkSequence", ({"name": "badge_seq", "nextVal": {"increment": 1}},)
    )
    with pytest.raises(WriteLoweringError, match=r"unsupported DB-computed marker.*'increment'"):
        _lower(insert, PK_SEQUENCE)


def test_computed_marker_reaching_an_update_is_refused() -> None:
    update = KeyedWrite("update", "Attendee", ({"id": 1, "name": {"computed": "maxPlusOne"}},))
    with pytest.raises(WriteLoweringError, match=r"unsupported DB-computed marker.*'computed'"):
        _lower(update, PK_MAX)


def test_unrecognized_computed_strategy_is_refused() -> None:
    insert = KeyedWrite(
        "insert", "Attendee", ({"id": {"computed": "somethingElse"}, "name": "Ada"},)
    )
    with pytest.raises(WriteLoweringError, match="not a recognized `computed` strategy"):
        _lower(insert, PK_MAX)


def test_a_mapping_that_does_not_match_the_one_key_marker_shape_binds_literally() -> None:
    # `_marker_kind`'s SHAPE classification (m-value-object "Writing" marker
    # disambiguation) requires EXACTLY one key naming a recognized marker —
    # a differently-shaped mapping (here, two keys) is neither a marker nor a
    # value-object document (which would already be JsonDocument-wrapped by
    # this point), so it is bound as an ordinary literal, never refused.
    update = KeyedWrite(
        "update", "Attendee", ({"id": 1, "name": {"computed": "maxPlusOne", "extra": True}},)
    )
    statement = _lower(update, PK_MAX)[0]
    assert statement.sql == "update attendee set name = ? where id = ?"
    assert statement.binds == ({"computed": "maxPlusOne", "extra": True}, 1)


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


def test_temporal_entity_write_is_refused() -> None:
    insert = KeyedWrite("insert", "Balance", ({"id": 9, "acctNum": "D", "value": 100.00},))
    with pytest.raises(WriteLoweringError, match="temporal write"):
        _lower(insert, BALANCE)


def test_temporal_inheritance_family_write_is_refused_with_the_temporal_message() -> None:
    # ADR 0026 / review remediation (Spec 1, consequence (c)): `DepositRate`
    # declares NO `as_of_attributes` of its own (only its family root `Rate`
    # does), so classifying from `entity.is_temporal` alone would miss it —
    # the write is still refused (temporal writes stay out of scope this
    # increment; only NON-temporal inheritance writes landed), but MUST be
    # refused with the byte-stable TEMPORAL message (`entity.temporal`
    # resolved through the family), never a generic inheritance-family one a
    # local-only check would emit instead.
    insert = KeyedWrite("insert", "DepositRate", ({"id": 1, "amount": 1.00, "grade": "A"},))
    with pytest.raises(WriteLoweringError, match=r"temporal write on 'DepositRate' \(bitemporal\)"):
        _lower(insert, RATE)


def test_milestone_verb_on_a_non_temporal_entity_is_refused() -> None:
    with pytest.raises(WriteLoweringError, match="temporal milestone verb"):
        _lower(KeyedWrite("terminate", "Account", ({"id": 1},)), ACCOUNT)


def test_business_bound_on_a_non_temporal_entity_is_refused() -> None:
    insert = KeyedWrite("insert", "Account", ({"id": 1, "balance": 1.00},), business_from=_B1)
    with pytest.raises(WriteLoweringError, match="business bound"):
        _lower(insert, ACCOUNT)


def test_multi_row_keyed_write_is_refused() -> None:
    # This seam lowers single-row keyed writes only; a multi-row instruction's
    # set-based collapse is m-batch-write (increment 5). Refusing loudly
    # prevents the silent rows[0]-only lowering the backbone review caught
    # (dropped later rows). The conformance engine never constructs one
    # (COR-3 Phase 8 increment 3 splits a case's batched `rows` into separate
    # single-row instructions before this seam ever sees them).
    insert = KeyedWrite(
        "insert",
        "Account",
        (
            {"id": 8, "owner": "Ada", "balance": 1.00, "version": 1},
            {"id": 9, "owner": "Grace", "balance": 2.00, "version": 1},
        ),
    )
    with pytest.raises(WriteLoweringError, match=r"multi-row keyed 'insert'.*m-batch-write"):
        _lower(insert, ACCOUNT)


def test_value_object_document_is_not_mistaken_for_a_marker() -> None:
    # The marker check classifies by SHAPE (a wrapped JsonDocument is never a
    # Mapping), not member role: a value-object member's whole-document mapping
    # still lowers to one JsonDocument bind, even marker-shaped.
    insert = KeyedWrite(
        "insert", "Customer", ({"id": 5, "name": "Vera", "address": {"city": "Berlin"}},)
    )
    statement = _lower(insert, CUSTOMER)[0]
    assert statement.binds[-1] == JsonDocument({"city": "Berlin"})
