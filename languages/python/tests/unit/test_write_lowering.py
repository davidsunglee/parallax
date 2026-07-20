"""Write-DML lowering unit tests (the composition seam, m-sql write DML).

``parallax.snapshot.handle.lower_write`` is the single write-lowering function both
the developer transaction path and the conformance engine reuse. These tests pin
its byte-exact non-temporal keyed emissions against the corpus goldens
(``m-unit-work-001/003/005``, ``m-opt-lock-002/005/006/013``,
``m-inheritance-007/008/009/010/084/104``, ``m-pk-gen-001``), compose it with the
M3 planner for the coalescing / mixed-flush / cancellation cases
(``-008/-009/-010``), pin the ``m-opt-lock`` version gate/advance/conflict policy
(observation-required for BOTH update and delete, gate-optimistic-only, a
row-carried version value refused outright, the derived initial version), the
inheritance tag derivation/guard/opt-lock composition, and the pk-gen
``max``/``increment`` marker lowering; the TEMPORAL keyed forms (COR-3 Phase 8
increment 4: close-and-chain, the rectangle split, the observed-``in_z``/business-
discriminator gate, `StaleWriteError` vs `OptimisticLockConflictError`) are pinned
in ``test_temporal_write_lowering.py``. Every remaining not-yet-lowered form
(predicate-selected, multi-row batch, an unrecognized marker) is refused with a
loud ``WriteLoweringError`` — never a wrong emission — mirroring the read
compiler's forward-error posture.
"""

from __future__ import annotations

from collections.abc import Mapping

import pytest

from parallax.conformance import models
from parallax.core import descriptor, opt_lock
from parallax.core import op_algebra as oa
from parallax.core.db_port import JsonDocument
from parallax.core.descriptor import Metamodel
from parallax.core.dialect import POSTGRES, Dialect
from parallax.core.sql_gen import Statement
from parallax.core.unit_work import (
    Concurrency,
    KeyedWrite,
    ObjectKey,
    Observation,
    PlannedWrite,
    PredicateWrite,
    WriteAssignment,
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
PAYMENT = _MODELS["payment"]
VEHICLE = _MODELS["vehicle"]
APPLIANCE = _MODELS["appliance"]
DOCUMENT = _MODELS["document"]
PK_MAX = _MODELS["pk-max"]
PK_SEQUENCE = _MODELS["pk-sequence"]
WALLET = _MODELS["wallet"]


def _lower(
    instruction: WriteInstruction,
    meta: Metamodel,
    *,
    observation: Observation | None = None,
    dialect: Dialect = POSTGRES,
    concurrency: Concurrency = "locking",
    tx_instant: str | None = None,
) -> list[Statement]:
    return [
        lowered.statement
        for lowered in lower_write(
            PlannedWrite(instruction=instruction, observation=observation),
            meta,
            dialect,
            concurrency,
            tx_instant,
        )
    ]


def _flush_and_lower(
    buffer: list[WriteInstruction],
    meta: Metamodel,
    *,
    concurrency: Concurrency = "locking",
    observations: Mapping[ObjectKey, Observation] | None = None,
) -> list[Statement]:
    plan = plan_flush(buffer, observations or {}, None, meta)
    return [
        lowered.statement
        for planned in plan.writes
        for lowered in lower_write(planned, meta, POSTGRES, concurrency)
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
    # m-unit-work-005 step 1: the version advances from this unit of work's own
    # recorded observation (`m-opt-lock`), never a row-carried value.
    statement = _lower(
        KeyedWrite("update", "Account", ({"id": 1, "balance": 175.00},)),
        ACCOUNT,
        observation=Observation(version=1),
    )[0]
    assert statement.sql == "update account set balance = ?, version = ? where id = ?"
    assert statement.binds == (175.00, 2, 1)


def test_delete_is_keyed_by_the_primary_key() -> None:
    # m-unit-work-007's own delete shape: a NON-versioned entity's keyed delete
    # is a bare `delete ... where <pk> = ?`, no opt-lock participation at all
    # (the versioned delete's own observation requirement is pinned below).
    statement = _lower(KeyedWrite("delete", "OrderItem", ({"id": 200},)), ORDERS)[0]
    assert statement.sql == "delete from order_item where id = ?"
    assert statement.binds == (200,)


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


def test_versioned_update_carrying_a_literal_version_is_refused() -> None:
    # A row that still authors the version attribute is refused outright
    # (`m-opt-lock` "Version values are framework-owned") — the framework-owned
    # field is never caller data, so it is never silently double-assigned
    # against the derived advance, EVEN when an observation is also available.
    update = KeyedWrite("update", "Account", ({"id": 1, "balance": 175.00, "version": 2},))
    with pytest.raises(opt_lock.CallerAuthoredVersionError, match="framework-owned"):
        _lower(update, ACCOUNT, observation=Observation(version=1), concurrency="optimistic")


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


def test_versioned_delete_without_an_observation_requires_observation() -> None:
    # A keyed DELETE of a versioned row this unit of work never observed raises
    # in EITHER mode, exactly as a keyed UPDATE does (m-opt-lock; python.md §5
    # "A keyed update or delete of a versioned row this unit of work never
    # observed raises in either mode") — the framework never issues an implicit
    # resolving read on behalf of a keyed write.
    delete = KeyedWrite("delete", "Account", ({"id": 3},))
    with pytest.raises(opt_lock.UnobservedVersionError, match="prior transaction-scoped"):
        _lower(delete, ACCOUNT, concurrency="optimistic")


def test_versioned_delete_without_an_observation_raises_in_locking_mode_too() -> None:
    delete = KeyedWrite("delete", "Account", ({"id": 3},))
    with pytest.raises(opt_lock.UnobservedVersionError, match="prior transaction-scoped"):
        _lower(delete, ACCOUNT, concurrency="locking")


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
    # m-unit-work-009: three objects, one flush, canonical combined order. BOTH
    # the update's and the delete's version (m-opt-lock's own prior-observation
    # requirement) come from THIS unit of work's own recorded observation —
    # never a row-carried value.
    statements = _flush_and_lower(
        [
            KeyedWrite(
                "insert", "Account", ({"id": 9, "owner": "Noether", "balance": 5.00, "version": 1},)
            ),
            KeyedWrite("update", "Account", ({"id": 1, "balance": 20.00},)),
            KeyedWrite("delete", "Account", ({"id": 3},)),
        ],
        ACCOUNT,
        observations={
            ("Account", (("id", 1),)): Observation(version=1),
            ("Account", (("id", 3),)): Observation(version=1),
        },
    )
    assert [(s.sql, s.binds) for s in statements] == [
        (
            "insert into account(id, owner, balance, version) values (?, ?, ?, ?)",
            (9, "Noether", 5.00, 1),
        ),
        ("update account set balance = ?, version = ? where id = ?", (20.00, 2, 1)),
        ("delete from account where id = ? and version = ?", (3, 1)),
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
def test_materializing_predicate_write_reaching_lower_write_is_refused() -> None:
    # A predicate write on a VERSIONED (or temporal) target never reaches
    # `lower_write` directly in production — materialization decomposes it to
    # per-row keyed writes at BUFFER time (`Transaction._buffer_predicate`,
    # ADR 0014), before it is ever planned. Reaching here with one is a
    # caller wiring defect this seam still refuses loudly, never mis-emits.
    predicate = PredicateWrite("delete", WriteTarget("Account", oa.All()))
    with pytest.raises(WriteLoweringError, match="materialize to keyed writes"):
        _lower(predicate, ACCOUNT)


def test_multi_row_insert_with_differing_row_shapes_is_refused() -> None:
    # m-batch-write's collapse eligibility groups only rows carrying the SAME
    # members, so a mixed-shape collapsed instruction is a caller wiring defect
    # — but a silent one: the emitted INSERT names the FIRST row's columns, so
    # every later value tuple would bind positionally against a column list it
    # does not match (here `balance`'s hole would take `Omar`'s absent member).
    # `lower_multi_insert` refuses instead of mis-emitting.
    mixed = KeyedWrite(
        "insert",
        "Wallet",
        (
            {"id": 10, "owner": "Mira", "balance": 100.00},
            {"id": 11, "owner": "Omar"},
        ),
    )
    with pytest.raises(WriteLoweringError, match="row column sets differ"):
        _lower(mixed, WALLET)


def test_milestone_verb_on_a_non_temporal_entity_is_refused() -> None:
    # The temporal milestone verb set (terminate / *Until) stays refused on a
    # NON-temporal entity — permanently: `Account` has no processing/business
    # axis to close, so a milestone verb aimed at it is never sensible,
    # regardless of which increment implements temporal writes.
    with pytest.raises(WriteLoweringError, match="temporal milestone verb"):
        _lower(KeyedWrite("terminate", "Account", ({"id": 1},)), ACCOUNT)


def test_multi_row_insert_collapses_to_one_statement_many_value_tuples() -> None:
    # m-batch-write-001's own insert entry: the multi-row INSERT collapse
    # renders ONE statement with one value tuple per row, in row order —
    # `_lower_multi_insert`'s own m-batch-write set-based flush.
    insert = KeyedWrite(
        "insert",
        "Wallet",
        (
            {"id": 10, "owner": "Mira", "balance": 100.00},
            {"id": 11, "owner": "Omar", "balance": 20.00},
        ),
    )
    statement = _lower(insert, WALLET)[0]
    assert statement.sql == "insert into wallet(id, owner, balance) values (?, ?, ?), (?, ?, ?)"
    assert statement.binds == (10, "Mira", 100.00, 11, "Omar", 20.00)


def test_multi_row_insert_on_a_versioned_entity_derives_initial_version_per_row() -> None:
    # `_lower_multi_insert`'s versioned-entity branch mirrors `_lower_insert`'s
    # single-row one (`handle.py:506-507`): every collapsed row derives the SAME
    # `opt_lock.INITIAL_VERSION` at the version column's family columnOrder
    # position, ignoring any row-carried value — a batched insert is exactly as
    # safe as a single-row one because the initial version is a constant, never
    # observed. No corpus witness collapses a multi-row insert on a versioned
    # entity (Wallet/Customer, m-batch-write-001/m-value-object-045, are both
    # non-versioned), so this is a unit-level pin.
    insert = KeyedWrite(
        "insert",
        "Account",
        (
            {"id": 20, "owner": "Curie", "balance": 10.00},
            {"id": 21, "owner": "Bohr", "balance": 20.00, "version": 99},
        ),
    )
    statement = _lower(insert, ACCOUNT)[0]
    assert (
        statement.sql
        == "insert into account(id, owner, balance, version) values (?, ?, ?, ?), (?, ?, ?, ?)"
    )
    assert statement.binds == (
        20,
        "Curie",
        10.00,
        opt_lock.INITIAL_VERSION,
        21,
        "Bohr",
        20.00,
        opt_lock.INITIAL_VERSION,
    )


def test_batched_update_collapses_to_one_in_list_statement() -> None:
    # m-batch-write-001's own update entry: a UNIFORM-value multi-row UPDATE
    # collapses to one `set ... where id in (...)` statement.
    update = KeyedWrite(
        "update",
        "Wallet",
        ({"id": 10, "balance": 500.00}, {"id": 11, "balance": 500.00}),
    )
    statement = _lower(update, WALLET)[0]
    assert statement.sql == "update wallet set balance = ? where id in (?, ?)"
    assert statement.binds == (500.00, 10, 11)


def test_multi_row_delete_collapses_to_one_in_list_statement() -> None:
    # m-batch-write-003: a non-versioned target's multi-row DELETE collapses
    # to one `delete ... where id in (...)` statement.
    delete = KeyedWrite("delete", "Wallet", ({"id": 1}, {"id": 2}, {"id": 3}))
    statement = _lower(delete, WALLET)[0]
    assert statement.sql == "delete from wallet where id in (?, ?, ?)"
    assert statement.binds == (1, 2, 3)


def test_batched_writes_on_an_inheritance_participant_carry_the_family_tag_guard() -> None:
    # A collapsed IN-list statement reuses the SAME family tag guard the
    # single-row identity predicate carries (`_tag_guard`). CardPayment and
    # CashPayment share the `payment` table, so an UNGUARDED
    # `delete from payment where id in (...)` would remove a sibling subtype's
    # rows whose ids happen to be in the list — the tag is what keeps a batch
    # collapse inside one concrete subtype.
    delete = KeyedWrite("delete", "CardPayment", ({"id": 1}, {"id": 2}))
    statement = _lower(delete, PAYMENT)[0]
    assert statement.sql == "delete from payment where id in (?, ?) and kind = ?"
    assert statement.binds == (1, 2, "card")

    update = KeyedWrite(
        "update", "CardPayment", ({"id": 1, "amount": 5.00}, {"id": 2, "amount": 5.00})
    )
    updated = _lower(update, PAYMENT)[0]
    assert updated.sql == "update payment set amount = ? where id in (?, ?) and kind = ?"
    assert updated.binds == (5.00, 1, 2, "card")


# A COMPOSITE-key entity: the corpus declares none, but a composite primary key
# is an ordinary well-formed model, and `_keys_in_list` renders it as a row-
# constructor IN-list rather than the single-column form.
_LEDGER = descriptor.Metamodel(
    entities=(
        descriptor.Entity(
            name="LedgerEntry",
            table="ledger_entry",
            mutability="transactional",
            attributes=(
                descriptor.Attribute(
                    name="bookId", type="int64", column="book_id", primary_key=True
                ),
                descriptor.Attribute(
                    name="lineNo", type="int64", column="line_no", primary_key=True
                ),
                descriptor.Attribute(name="amount", type="decimal(18,2)", column="amount"),
            ),
        ),
    )
)


def test_multi_row_delete_on_a_composite_key_uses_a_row_constructor_in_list() -> None:
    # `(<pk1>, <pk2>) in ((?, ?), …)`, one entry per row in row order, binds
    # grouped per row in key-declaration order — never the single-column
    # `<pk> in (?, …)` form, which would silently key on `book_id` alone and
    # delete every line of the book.
    delete = KeyedWrite(
        "delete", "LedgerEntry", ({"bookId": 7, "lineNo": 1}, {"bookId": 7, "lineNo": 2})
    )
    statement = _lower(delete, _LEDGER)[0]
    assert statement.sql == "delete from ledger_entry where (book_id, line_no) in ((?, ?), (?, ?))"
    assert statement.binds == (7, 1, 7, 2)


def test_readless_predicate_delete_lowers_to_one_statement() -> None:
    # m-batch-write-005: an unversioned, non-temporal target's predicate
    # delete is readless — one statement, no materialization, unaliased
    # predicate rendering (contrast the resolving read's `t0`-aliased form).
    predicate = PredicateWrite(
        "delete",
        WriteTarget("Wallet", oa.Comparison(op="lessThan", attr="Wallet.balance", value=200.00)),
    )
    statement = _lower(predicate, WALLET)[0]
    assert statement.sql == "delete from wallet where balance < ?"
    assert statement.binds == (200.00,)


def test_readless_predicate_update_follows_declared_column_order() -> None:
    # m-batch-write-006: reversed authored assignments (balance then owner)
    # still emit descriptor DECLARED column order (owner then balance) —
    # assignment binds in emitted column order, predicate binds after.
    predicate = PredicateWrite(
        "update",
        WriteTarget("Wallet", oa.Comparison(op="lessThan", attr="Wallet.balance", value=200.00)),
        assignments=(
            WriteAssignment(attr="Wallet.balance", value=150.00),
            WriteAssignment(attr="Wallet.owner", value="Updated"),
        ),
    )
    statement = _lower(predicate, WALLET)[0]
    assert statement.sql == "update wallet set owner = ?, balance = ? where balance < ?"
    assert statement.binds == ("Updated", 150.00, 200.00)


def test_value_object_document_is_not_mistaken_for_a_marker() -> None:
    # The marker check classifies by SHAPE (a wrapped JsonDocument is never a
    # Mapping), not member role: a value-object member's whole-document mapping
    # still lowers to one JsonDocument bind, even marker-shaped.
    insert = KeyedWrite(
        "insert", "Customer", ({"id": 5, "name": "Vera", "address": {"city": "Berlin"}},)
    )
    statement = _lower(insert, CUSTOMER)[0]
    assert statement.binds[-1] == JsonDocument({"city": "Berlin"})
