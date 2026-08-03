"""Write-DML lowering unit tests (the composition seam, m-sql write DML).

``parallax.snapshot.handle.stream_lowered`` is the single write-lowering seam both
the developer transaction path and the conformance engine reuse. These tests pin
its byte-exact non-temporal keyed emissions against the corpus goldens
(``m-unit-work-001/003/005``, ``m-opt-lock-002/005/006/013``,
``m-inheritance-007/008/009/010/084/104``, ``m-pk-gen-001``), compose it with the
Write Planner for the coalescing / mixed-flush / cancellation cases
(``-008/-009/-010``), pin the ``m-opt-lock`` version gate/advance/shortfall
policy (observation-required for BOTH update and delete, gate-optimistic-only, a
row-carried version value refused outright, the derived initial version), the
inheritance tag derivation/guard/opt-lock composition, and the pk-gen
``max``/``increment`` marker lowering. The temporal keyed forms—close-and-chain,
the rectangle split, the per-axis close address, the observed-``in_z`` gate, and
the settled ``StaleWrite`` versus ``OptimisticConflict`` shortfall tag—are pinned
in ``test_temporal_write_lowering.py``. The predicate-selected and multi-row batch
forms use the same lowering seam. Planning refuses a materializing predicate write
that reaches it, a mixed-shape multi-row instruction, a milestone verb on a
non-temporal entity, and an unsupported DB-computed marker with a loud
``WritePlanningError``; lowering separately refuses a target with no effective
table with ``WriteLoweringError`` — each a forward-error posture, never a wrong
emission, mirroring the read compiler's own.

The final section pins the two halves the non-temporal insert family crosses
separately: the Write Planner settling an instruction into finalized steps, and
``_step_lowering.lower_step`` rendering a step built by hand — proving that
lowering answers a purely physical question and never re-derives a semantic one.
The composed emissions above are the byte-exact evidence; these are the seam
itself.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Mapping
from types import MappingProxyType
from typing import cast

import pytest
from _metamodel_support import Declaration, attribute, identity, key, source

from _support.clock_probes import inert_instant
from _support.lowering_probes import lower_instruction, lower_instruction_steps
from _support.planner_probes import TEST_SUBJECT_IDENTITY
from parallax.conformance import models
from parallax.core import inheritance, opt_lock, storage_layout
from parallax.core import op_algebra as oa
from parallax.core._formation_profile import form_metamodel
from parallax.core.base import STRING
from parallax.core.db_port import JsonDocument
from parallax.core.dialect import POSTGRES, Dialect
from parallax.core.metamodel import (
    AttributeIdentity,
    EntityIdentity,
    Multiplicity,
    ValueObjectAttributeDeclaration,
    ValueObjectIdentity,
    ValueObjectOccurrenceDeclaration,
    ValueObjectShapeDeclaration,
    ValueObjectShapeKey,
    entity_by_name,
)
from parallax.core.metamodel import Column as CoreColumn
from parallax.core.metamodel import Table as CoreTable
from parallax.core.model_formation import MetamodelValidationError
from parallax.core.sql_gen import Statement
from parallax.core.unit_work import (
    ANY_COUNT,
    MAX_PLUS_ONE,
    MISSING_TARGET,
    NEW_LINEAGE,
    OPTIMISTIC_CONFLICT,
    STALE_WRITE,
    UNGATED,
    UNVERSIONED,
    Concurrency,
    ExactCount,
    InsertEntry,
    KeyedWrite,
    KeyTarget,
    ObjectKey,
    PlannedAssignments,
    PlannedDelete,
    PlannedInsert,
    PlannedRow,
    PlannedUpdate,
    PlanningRequest,
    PredicateSelection,
    PredicateTarget,
    PredicateWrite,
    SelfIncrement,
    Versioned,
    VersionGate,
    VersionObservation,
    WriteAssignment,
    WriteInstruction,
    WriteObservation,
    WritePlanningError,
)
from parallax.core.unit_work.planned import PlannedWrite as PlannedStep
from parallax.descriptor import _records
from parallax.descriptor._records import Metamodel
from parallax.snapshot.handle import WriteLoweringError, build_write_planner, stream_lowered
from parallax.snapshot.handle._step_lowering import lower_step

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
BALANCE = _MODELS["balance"]


def _lower(
    instruction: WriteInstruction,
    meta: Metamodel,
    *,
    observation: WriteObservation | None = None,
    dialect: Dialect = POSTGRES,
    concurrency: Concurrency = "locking",
) -> list[Statement]:
    model = models.accepted_model(meta)
    return lower_instruction(instruction, model, dialect, concurrency, observation=observation)


def _flush_and_lower(
    buffer: list[WriteInstruction],
    meta: Metamodel,
    *,
    concurrency: Concurrency = "locking",
    observations: Mapping[ObjectKey, WriteObservation] | None = None,
) -> list[Statement]:
    model = models.accepted_model(meta)
    instant = inert_instant()
    plan = build_write_planner(model).plan(
        PlanningRequest(
            subject_identity=TEST_SUBJECT_IDENTITY,
            transaction_instant=instant,
            concurrency=concurrency,
            buffered_writes=buffer,
            observations=observations or {},
        )
    )
    return [statement for _step, statement in stream_lowered(plan, model, POSTGRES)]


def _layout_columns(meta: Metamodel, entity_name: str) -> tuple[str, ...]:
    """The target Entity's applicable Table Layout slots, in canonical order."""
    model = models.accepted_model(meta)
    metadata = entity_by_name(model, entity_name)
    assert metadata is not None
    view = storage_layout.view(model).entity(metadata.identity)
    assert view is not None
    return tuple(slot.column.name for slot in view.columns)


def _insert_columns(statement: Statement) -> tuple[str, ...]:
    columns = statement.sql.split("(", 1)[1].split(")", 1)[0]
    return tuple(column.strip() for column in columns.split(","))


def test_non_temporal_write_requires_an_effective_table() -> None:
    account = dataclasses.replace(ACCOUNT.entity("Account"), table=None)
    malformed = Metamodel(entities=(account,))
    with pytest.raises(WriteLoweringError, match="write target has no effective table"):
        _lower(KeyedWrite("insert", "Account", ({"id": 1},)), malformed)


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
    # the Entity Layout's slots (orderedOn -> ordered_on last among Order's scalars).
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
        observation=VersionObservation(observed_version=1),
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
    # A value-object member rides its Document-tier slot as one JsonDocument — the
    # whole document, never decomposed (m-sql valueObject atomic document write).
    # The document is COMPOSED through the codec rather than bound as the write
    # input carried it, so presence is the codec's answer: `phones` is a `many`
    # occurrence and always contributes its array, the sole zero-element
    # representation, exactly as the developer path's `to_document` already did.
    statement = _lower(
        KeyedWrite("insert", "Customer", ({"id": 1, "name": "Ada", "address": {"city": "Oslo"}},)),
        CUSTOMER,
    )[0]
    assert statement.sql == "insert into customer(id, name, address) values (?, ?, ?)"
    assert statement.binds[:2] == (1, "Ada")
    assert statement.binds[2] == JsonDocument({"city": "Oslo", "phones": []})


def test_a_value_object_leaf_binds_the_codecs_spelling_not_the_write_inputs() -> None:
    # The write input carries each leaf in its portable wire spelling; what the
    # statement binds is the ONE document spelling the codec owns, at every depth.
    # `elevation` is a `float64`, so the shortest round-tripping number replaces
    # the authored integer carrier rather than riding through to a serializer.
    statement = _lower(
        KeyedWrite(
            "insert",
            "Customer",
            (
                {
                    "id": 2,
                    "name": "Bo",
                    "address": {
                        "city": "Bergen",
                        "geo": {"country": "NO", "elevation": 12},
                        "phones": [{"type": "home", "number": "555-0100"}],
                    },
                },
            ),
        ),
        CUSTOMER,
    )[0]
    assert statement.binds[2] == JsonDocument(
        {
            "city": "Bergen",
            "geo": {"country": "NO", "elevation": 12.0},
            "phones": [{"type": "home", "number": "555-0100"}],
        }
    )


# --------------------------------------------------------------------------- #
# m-storage-layout: the one physical shape every keyed emission follows.       #
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    ("meta", "entity", "row"),
    [
        (
            ORDERS,
            "Order",
            {
                "id": 1,
                "name": "H",
                "sku": "X",
                "qty": 1,
                "price": 1.0,
                "active": True,
                "orderedOn": "2024-07-01",
            },
        ),
        (PAYMENT, "CardPayment", {"id": 1, "amount": 10.00, "cardNetwork": "Visa"}),
        (
            DOCUMENT,
            "Invoice",
            {"id": 1, "title": "T", "folderId": 9, "currency": "USD", "amountDue": 10.00},
        ),
    ],
)
def test_full_row_insert_emits_the_entity_layout_slot_selection(
    meta: Metamodel, entity: str, row: dict[str, object]
) -> None:
    # A row naming every applicable member emits exactly the target's Table Layout
    # slot selection, in slot order — a standalone Entity's own table, a
    # table-per-hierarchy concrete's applicable slots of the SHARED table (the
    # derived discriminator included, the sibling's own slot excluded), and a
    # table-per-concrete-subtype concrete's complete ancestry in its own table.
    statement = _lower(KeyedWrite("insert", entity, (row,)), meta)[0]
    assert _insert_columns(statement) == _layout_columns(meta, entity)


def test_update_sets_every_layout_slot_the_row_names_except_the_model_key() -> None:
    # The SET clause is the layout slot order filtered to the row's members, minus
    # the model key the predicate carries; the tag slot is a guard, never a SET
    # column, even though it precedes both domain slots in the shared table.
    statement = _lower(
        KeyedWrite("update", "CardPayment", ({"id": 1, "amount": 130.00, "cardNetwork": "Visa"},)),
        PAYMENT,
    )[0]
    assert _layout_columns(PAYMENT, "CardPayment") == ("id", "kind", "amount", "card_network")
    assert statement.sql == (
        "update payment set amount = ?, card_network = ? where id = ? and kind = ?"
    )
    assert statement.binds == (130.00, "Visa", 1, "card")


def test_multi_row_insert_column_list_is_the_shared_layout_slot_filter() -> None:
    # A collapsed multi-row INSERT emits ONE column list: the layout slot order
    # filtered to the members every row carries, with the derived discriminator at
    # its own slot in each value tuple.
    statement = _lower(
        KeyedWrite(
            "insert",
            "CardPayment",
            (
                {"id": 1, "amount": 10.00, "cardNetwork": "Visa"},
                {"cardNetwork": "Amex", "amount": 20.00, "id": 2},
            ),
        ),
        PAYMENT,
    )[0]
    assert _insert_columns(statement) == _layout_columns(PAYMENT, "CardPayment")
    assert statement.sql == (
        "insert into payment(id, kind, amount, card_network) values (?, ?, ?, ?), (?, ?, ?, ?)"
    )
    assert statement.binds == (1, "card", 10.00, "Visa", 2, "card", 20.00, "Amex")


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
    statement = _lower(
        update, ACCOUNT, observation=VersionObservation(observed_version=3), concurrency="locking"
    )[0]
    assert statement.sql == "update account set balance = ?, version = ? where id = ?"
    assert statement.binds == (50.00, 4, 1)


def test_versioned_update_gates_on_the_observed_version_optimistic_mode() -> None:
    # optimistic mode: SAME advance, plus `and version = ?` binding the observed
    # value LAST.
    update = KeyedWrite("update", "Account", ({"id": 1, "balance": 50.00},))
    statement = _lower(
        update,
        ACCOUNT,
        observation=VersionObservation(observed_version=3),
        concurrency="optimistic",
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
        _lower(
            update,
            ACCOUNT,
            observation=VersionObservation(observed_version=1),
            concurrency="optimistic",
        )


def test_versioned_delete_gates_on_the_observed_version_optimistic_mode() -> None:
    # m-opt-lock-015: optimistic mode binds the observed version LAST, exactly as
    # a versioned UPDATE's own gate does — the gate is concurrency-driven, never
    # mutation-driven.
    delete = KeyedWrite("delete", "Account", ({"id": 3},))
    statement = _lower(
        delete,
        ACCOUNT,
        observation=VersionObservation(observed_version=1),
        concurrency="optimistic",
    )[0]
    assert statement.sql == "delete from account where id = ? and version = ?"
    assert statement.binds == (3, 1)


def test_versioned_delete_is_ungated_in_locking_mode() -> None:
    # m-batch-write-004: locking mode renders NO gate on a versioned delete, the
    # same ungated form a versioned UPDATE and a temporal close take — the shared
    # read lock, not a version predicate, is what makes the write correct.
    delete = KeyedWrite("delete", "Account", ({"id": 3},))
    statement = _lower(
        delete, ACCOUNT, observation=VersionObservation(observed_version=1), concurrency="locking"
    )[0]
    assert statement.sql == "delete from account where id = ?"
    assert statement.binds == (3,)


def test_versioned_delete_shortfall_classifies_by_gate_not_by_mutation() -> None:
    # An ungated (locking-mode) shortfall is the NON-retriable stale outcome an
    # ungated close's is; a gated (optimistic) one stays the retriable conflict.
    delete = KeyedWrite("delete", "Account", ({"id": 3},))
    observation = VersionObservation(observed_version=1)
    model = models.accepted_model(ACCOUNT)
    locking, _ = lower_instruction_steps(
        delete, model, concurrency="locking", observation=observation
    )[0]
    optimistic, _ = lower_instruction_steps(
        delete, model, concurrency="optimistic", observation=observation
    )[0]
    assert isinstance(locking, PlannedDelete)
    assert isinstance(optimistic, PlannedDelete)
    assert locking.affected_rows == ExactCount(1, STALE_WRITE)
    assert optimistic.affected_rows == ExactCount(1, OPTIMISTIC_CONFLICT)


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
    # m-inheritance-084: the bind order end to end — pk, tag guard,
    # THEN the version gate (no inheritance exception to "the gate binds last").
    update = KeyedWrite("update", "Car", ({"id": 1, "name": "Coupe"},))
    statement = _lower(
        update,
        VEHICLE,
        observation=VersionObservation(observed_version=5),
        concurrency="optimistic",
    )[0]
    assert statement.sql == (
        "update vehicle set name = ?, version = ? where id = ? and kind = ? and version = ?"
    )
    assert statement.binds == ("Coupe", 6, 1, "car", 5)


def test_tpcs_optlock_composition_no_tag_guard_gate_binds_last() -> None:
    # m-inheritance-104: the TPCS analogue — no shared table, no tag, own table.
    update = KeyedWrite("update", "Fridge", ({"id": 1, "name": "Chill"},))
    statement = _lower(
        update,
        APPLIANCE,
        observation=VersionObservation(observed_version=5),
        concurrency="optimistic",
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
    with pytest.raises(WritePlanningError, match=r"unsupported DB-computed marker.*'increment'"):
        _lower(insert, PK_SEQUENCE)


def test_computed_marker_reaching_an_update_is_refused() -> None:
    update = KeyedWrite("update", "Attendee", ({"id": 1, "name": {"computed": "maxPlusOne"}},))
    with pytest.raises(WritePlanningError, match=r"unsupported DB-computed marker.*'computed'"):
        _lower(update, PK_MAX)


def test_unrecognized_computed_strategy_is_refused() -> None:
    insert = KeyedWrite(
        "insert", "Attendee", ({"id": {"computed": "somethingElse"}, "name": "Ada"},)
    )
    with pytest.raises(WritePlanningError, match="not a recognized `computed` strategy"):
        _lower(insert, PK_MAX)


def test_a_mapping_that_does_not_match_the_one_key_marker_shape_binds_literally() -> None:
    # `write_planner._marker`'s SHAPE classification (m-value-object "Writing"
    # marker disambiguation) requires EXACTLY one key naming a recognized marker —
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
    # never a row-carried value. Under the default locking mode neither renders
    # a gate.
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
            ("Account", (("id", 1),)): VersionObservation(observed_version=1),
            ("Account", (("id", 3),)): VersionObservation(observed_version=1),
        },
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
def test_materializing_predicate_write_reaching_finalization_is_refused() -> None:
    # A predicate write on a VERSIONED (or temporal) target never reaches
    # finalization directly in production — materialization decomposes it to
    # per-row keyed writes at BUFFER time (`parallax.snapshot.handle`'s
    # `buffer_predicate`, which the `_where` verbs only delegate to; ADR 0014),
    # before it is ever planned. Reaching here with one is a caller wiring
    # defect this seam still refuses loudly, never mis-emits.
    predicate = PredicateWrite("delete", PredicateSelection("Account", oa.All()))
    with pytest.raises(WritePlanningError, match="materialize to keyed writes"):
        _lower(predicate, ACCOUNT)


@pytest.mark.parametrize(
    "predicate",
    [
        # A bare family predicate: the guard is TARGET-driven, so the plainest
        # shape refuses too.
        oa.Comparison(op="eq", attr="CardPayment.cardNetwork", value="Visa"),
        # The shape that actually mis-emitted: a `narrow` renders the family's
        # framework-owned tag guard, which a read alias-qualifies.
        oa.Narrow(
            entity="Payment",
            to=("CardPayment",),
            operand=oa.Comparison(op="eq", attr="CardPayment.cardNetwork", value="Visa"),
        ),
    ],
    ids=["bare-predicate", "narrow"],
)
def test_inheritance_family_predicate_write_is_rejected_before_sql(
    predicate: oa.Operation,
) -> None:
    # `python.md` §5: "a set-based write whose target entity belongs to an
    # inheritance family is REJECTED BEFORE SQL with the corpus's
    # `subtype-write-set-based-unsupported` classification (m-inheritance-089)".
    #
    # The buffer-time seams (`_predicate_writes.buffer_predicate` /
    # `buffer_predicate_instruction`) guard the developer `_where` verbs and the
    # engine's buffering translation — but they are NOT on every road here.
    # `stream_lowered` is EXPORTED (`parallax.snapshot.handle.__all__`,
    # `tests/api/public_api.json`), and the conformance engine's readless
    # predicate-write step (`engine._lower_predicate_write_step`) reaches it
    # straight from a deserialized instruction. The lowering-side guard must
    # reject the `narrow` case before it can introduce an alias that unaliased
    # DML never declares (`m-sql` rule 1).
    write = PredicateWrite("delete", PredicateSelection("CardPayment", predicate))
    with pytest.raises(inheritance.InheritanceError) as excinfo:
        _lower(write, PAYMENT)
    assert excinfo.value.rule == "subtype-write-set-based-unsupported"


def test_multi_row_insert_with_differing_row_shapes_is_refused() -> None:
    # Batch grouping compares filtered slot selections
    # (`handle.collapse_group_key`), so no PLANNED instruction is ever
    # mixed-shape — a hand-built one is a caller wiring defect, and a silent
    # one: the emitted INSERT names the FIRST row's columns, so every later
    # value tuple would bind positionally against a column list it does not
    # match (here `balance`'s hole would take `Omar`'s absent member).
    # Uniform membership is a Planned Insert's own construction invariant, so
    # the mixed shape is refused while the step is being settled — before any
    # column list exists to mis-emit against.
    mixed = KeyedWrite(
        "insert",
        "Wallet",
        (
            {"id": 10, "owner": "Mira", "balance": 100.00},
            {"id": 11, "owner": "Omar"},
        ),
    )
    with pytest.raises(ValueError, match="names the same members"):
        _lower(mixed, WALLET)


def test_milestone_verb_on_a_non_temporal_entity_is_refused() -> None:
    # The temporal milestone verb set (terminate / *Until) stays refused on a
    # NON-temporal entity — permanently: `Account` has no Transaction-/Valid-Time
    # axis to close, so a milestone verb aimed at it is never sensible.
    with pytest.raises(WritePlanningError, match="temporal milestone verb"):
        _lower(KeyedWrite("terminate", "Account", ({"id": 1},)), ACCOUNT)


def test_multi_row_insert_collapses_to_one_statement_many_value_tuples() -> None:
    # m-batch-write-001's own insert entry: the multi-row INSERT collapse
    # renders ONE statement with one value tuple per row, in row order —
    # the m-batch-write set-based flush's own multi-entry insert.
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
    # the multi-entry insert's versioned-entity behavior mirrors the single row's
    # single-row one (`parallax.snapshot.handle`'s keyed-SQL builders): every
    # collapsed row derives the SAME `opt_lock.INITIAL_VERSION` at the version
    # column's own Table Layout slot position, ignoring any row-carried value — a
    # batched insert is exactly as safe as a single-row one because the initial
    # version is a constant, never observed. No corpus witness collapses a
    # multi-row insert on a versioned entity (Wallet/Customer,
    # m-batch-write-001/m-value-object-045, are both non-versioned), so this
    # is a unit-level pin.
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
# is an ordinary well-formed model, and a multi-key target renders it as a
# row-constructor IN-list rather than the single-column form.
_LEDGER = _records.Metamodel(
    entities=(
        _records.Entity(
            name="LedgerEntry",
            table="ledger_entry",
            attributes=(
                _records.Attribute(name="bookId", type="int64", column="book_id", primary_key=True),
                _records.Attribute(name="lineNo", type="int64", column="line_no", primary_key=True),
                _records.Attribute(name="amount", type="decimal(18,2)", column="amount"),
            ),
        ),
    )
)


def test_a_composite_primary_key_does_not_form() -> None:
    # The accepted Metamodel admits exactly one primary-key Attribute per
    # standalone Entity (m-metamodel `metamodel-primary-key-multiple`), so a
    # composite-key entity never forms and never reaches finalization — the
    # `(<pk1>, <pk2>) in (...)` row-constructor branch lowering keeps is
    # defensive under that contract.
    with pytest.raises(MetamodelValidationError, match="metamodel-primary-key-multiple"):
        models.accepted_model(_LEDGER)


def test_a_multi_column_key_target_renders_a_row_constructor() -> None:
    # The form that branch keeps: `(<pk1>, <pk2>) in ((?, ?), …)`, one tuple per
    # addressed row in planner order, key columns in the target's own order. No
    # accepted Metamodel can reach it through finalization (the rule above), so
    # the step is built by hand with a two-Attribute key.
    step = PlannedDelete(
        entity=_identity(WALLET, "Wallet"),
        target=KeyTarget(
            key_attributes=(
                _attribute(WALLET, "Wallet", "id"),
                _attribute(WALLET, "Wallet", "owner"),
            ),
            key_values=((1, "Ada"), (2, "Bo")),
        ),
        concurrency=UNVERSIONED,
        affected_rows=ExactCount(expected=2, on_shortfall=MISSING_TARGET),
    )
    statement = lower_step(step, models.accepted_model(WALLET), POSTGRES)
    assert statement.sql == "delete from wallet where (id, owner) in ((?, ?), (?, ?))"
    assert statement.binds == (1, "Ada", 2, "Bo")


def test_readless_predicate_delete_lowers_to_one_statement() -> None:
    # m-batch-write-005: an unversioned, non-temporal target's predicate
    # delete is readless — one statement, no materialization, unaliased
    # predicate rendering (contrast the resolving read's `t0`-aliased form).
    predicate = PredicateWrite(
        "delete",
        PredicateSelection(
            "Wallet", oa.Comparison(op="lessThan", attr="Wallet.balance", value=200.00)
        ),
    )
    statement = _lower(predicate, WALLET)[0]
    assert statement.sql == "delete from wallet where balance < ?"
    assert statement.binds == (200.00,)


def test_readless_predicate_update_follows_the_entity_layout_order() -> None:
    # m-batch-write-006: reversed authored assignments (balance then owner)
    # still emit the Entity Layout's slot order (owner then balance) —
    # assignment binds in emitted column order, predicate binds after.
    predicate = PredicateWrite(
        "update",
        PredicateSelection(
            "Wallet", oa.Comparison(op="lessThan", attr="Wallet.balance", value=200.00)
        ),
        assignments=(
            WriteAssignment(attr="Wallet.balance", value=150.00),
            WriteAssignment(attr="Wallet.owner", value="Updated"),
        ),
    )
    statement = _lower(predicate, WALLET)[0]
    assert statement.sql == "update wallet set owner = ?, balance = ? where balance < ?"
    assert statement.binds == ("Updated", 150.00, 200.00)


def test_value_object_document_is_not_mistaken_for_a_marker() -> None:
    # A DB-computed marker is a SCALAR cell's shape. A value-object member
    # resolves to its own Value Object identity, so its whole-document mapping is
    # never offered to the marker classification at all — it still lowers to one
    # JsonDocument bind, marker-shaped or not.
    insert = KeyedWrite(
        "insert", "Customer", ({"id": 5, "name": "Vera", "address": {"city": "Berlin"}},)
    )
    statement = _lower(insert, CUSTOMER)[0]
    assert statement.binds[-1] == JsonDocument({"city": "Berlin", "phones": []})


# --------------------------------------------------------------------------- #
# The finalized non-temporal insert: what settles the step, and what renders   #
# it. Everything above composes the two; these pin the split itself.           #
# --------------------------------------------------------------------------- #
def _finalize(
    instruction: WriteInstruction,
    meta: Metamodel,
    *,
    observation: WriteObservation | None = None,
    concurrency: Concurrency = "locking",
) -> tuple[PlannedStep, ...]:
    steps = lower_instruction_steps(
        instruction,
        models.accepted_model(meta),
        concurrency=concurrency,
        observation=observation,
    )
    return tuple(step for step, _statement in steps)


def _identity(meta: Metamodel, entity: str) -> EntityIdentity:
    metadata = entity_by_name(models.accepted_model(meta), entity)
    assert metadata is not None
    return metadata.identity


def _attribute(meta: Metamodel, entity: str, member: str) -> AttributeIdentity:
    """The Attribute identity a write row's ``member`` spelling names — the
    family-effective one, so an inherited member resolves at its declaring
    ancestor exactly as the Table Layout slot's own contributor does."""
    model = models.accepted_model(meta)
    position = inheritance.view(model).entity(_identity(meta, entity))
    assert position is not None
    attribute = position.applicable_attribute(member)
    assert attribute is not None
    return attribute.identity


def _value_object(meta: Metamodel, entity: str, member: str) -> ValueObjectIdentity:
    model = models.accepted_model(meta)
    position = inheritance.view(model).entity(_identity(meta, entity))
    assert position is not None
    value_object = position.applicable_value_object(member)
    assert value_object is not None
    return value_object.identity


def test_step_lowering_reads_an_immutable_write_input_into_a_plain_json_document() -> None:
    # A Planned Row freezes what it carries, so the occurrence arrives as a
    # read-only mapping over read-only elements. The codec READS it and builds the
    # document, so what crosses the bind seam is a plain JSON structure the driver
    # can serialize rather than the frozen carriers the planner held.
    row = PlannedRow(
        attributes={
            _attribute(CUSTOMER, "Customer", "id"): 1,
            _attribute(CUSTOMER, "Customer", "name"): "Ada",
        },
        value_objects={
            _value_object(CUSTOMER, "Customer", "address"): MappingProxyType(
                {
                    "city": "Oslo",
                    "phones": (
                        MappingProxyType({"type": "home"}),
                        MappingProxyType({"type": "work"}),
                    ),
                }
            )
        },
    )
    step = PlannedInsert(
        entity=_identity(CUSTOMER, "Customer"),
        entries=(InsertEntry(row=row, origin=NEW_LINEAGE),),
    )

    statement = lower_step(step, models.accepted_model(CUSTOMER), POSTGRES)

    assert statement.binds[-1] == JsonDocument(
        {"city": "Oslo", "phones": [{"type": "home"}, {"type": "work"}]}
    )
    document = cast("JsonDocument", statement.binds[-1]).value
    assert type(document) is dict
    assert type(cast("dict[str, object]", document)["phones"]) is list


def test_finalization_settles_an_insert_into_one_step_of_new_lineage_entries() -> None:
    steps = _finalize(
        KeyedWrite("insert", "Wallet", ({"id": 10, "owner": "Mira", "balance": 100.00},)),
        WALLET,
    )
    assert steps is not None
    (step,) = steps
    assert step == PlannedInsert(
        entity=_identity(WALLET, "Wallet"),
        entries=(
            InsertEntry(
                row=PlannedRow(
                    attributes={
                        _attribute(WALLET, "Wallet", "id"): 10,
                        _attribute(WALLET, "Wallet", "owner"): "Mira",
                        _attribute(WALLET, "Wallet", "balance"): 100.00,
                    }
                ),
                origin=NEW_LINEAGE,
            ),
        ),
    )


def test_finalization_derives_the_initial_version_the_row_never_authors() -> None:
    # The version is framework-owned end to end (ADR 0013): the settled step
    # already carries it, so nothing downstream re-derives it from the model.
    steps = _finalize(
        KeyedWrite("insert", "Account", ({"id": 9, "owner": "Noether", "balance": 5.00},)),
        ACCOUNT,
    )
    assert steps is not None
    (step,) = steps
    assert isinstance(step, PlannedInsert)
    row = step.entries[0].row
    assert row.attributes[_attribute(ACCOUNT, "Account", "version")] == opt_lock.INITIAL_VERSION


def test_finalization_classifies_a_pk_gen_marker_into_a_generated_value() -> None:
    # The authored marker document is classified ONCE, while the step is being
    # settled; the rendered statement reads a closed generated-value expression
    # rather than re-inspecting a mapping's shape.
    steps = _finalize(
        KeyedWrite("insert", "Attendee", ({"id": {"computed": "maxPlusOne"}, "name": "Ada"},)),
        PK_MAX,
    )
    assert steps is not None
    (step,) = steps
    assert isinstance(step, PlannedInsert)
    row = step.entries[0].row
    assert row.attributes[_attribute(PK_MAX, "Attendee", "id")] == MAX_PLUS_ONE


@pytest.mark.parametrize(
    "value",
    [
        {"computed": "maxPlusOne", "extra": True},
        {"allocated": "maxPlusOne"},
    ],
    ids=["two-key", "unrecognized-key"],
)
def test_a_mapping_outside_the_marker_shape_stays_an_ordinary_insert_cell(
    value: dict[str, object],
) -> None:
    # Marker classification requires EXACTLY one key naming a recognized marker.
    # A differently shaped mapping is neither a marker nor a value-object
    # document (its member is a scalar Attribute), so it stays a literal bind
    # rather than earning a refusal.
    statement = _lower(KeyedWrite("insert", "Attendee", ({"id": 1, "name": value},)), PK_MAX)[0]
    assert statement.sql == "insert into attendee(id, name) values (?, ?)"
    assert statement.binds == (1, value)


def test_a_write_row_naming_no_family_member_is_refused_at_finalization() -> None:
    # Every member spelling must resolve to a semantic identity before a step
    # exists, so an unknown one is refused where the resolution happens — never
    # silently dropped from the emitted column list.
    with pytest.raises(WritePlanningError, match="not a member of the Entity's family"):
        _finalize(KeyedWrite("insert", "Wallet", ({"id": 10, "nickname": "M"},)), WALLET)


def test_a_milestone_verb_on_a_non_temporal_entity_is_refused_at_finalization() -> None:
    # A milestone verb opens, splits, or closes a milestone, and an Entity
    # declaring no as-of axis has none — refused where the target's family is
    # resolved, never rendered as an ordinary keyed write.
    with pytest.raises(WritePlanningError, match="declares no temporal dimension"):
        _finalize(KeyedWrite("terminate", "Account", ({"id": 1},)), ACCOUNT)


def test_finalization_settles_an_addressed_update_into_target_gate_and_policy() -> None:
    # One step carries the whole decision: which rows it addresses, the gate the
    # mode chose, the advance that rides the assignments, and how a shortfall
    # against its expected effect classifies.
    steps = _finalize(
        KeyedWrite("update", "Account", ({"id": 1, "balance": 175.00},)),
        ACCOUNT,
        observation=VersionObservation(observed_version=3),
        concurrency="optimistic",
    )
    assert steps is not None
    version = _attribute(ACCOUNT, "Account", "version")
    assert steps == (
        PlannedUpdate(
            entity=_identity(ACCOUNT, "Account"),
            target=KeyTarget(
                key_attributes=(_attribute(ACCOUNT, "Account", "id"),), key_values=((1,),)
            ),
            assignments=PlannedAssignments(
                attributes={_attribute(ACCOUNT, "Account", "balance"): 175.00, version: 4}
            ),
            concurrency=Versioned(gate=VersionGate(attribute=version, observed_version=3)),
            affected_rows=ExactCount(expected=1, on_shortfall=OPTIMISTIC_CONFLICT),
        ),
    )


def test_finalization_records_an_explicit_ungated_decision_under_locking() -> None:
    # Locking mode records `Ungated` rather than a null gate, and the version
    # still advances — the advance is an assignment, never a gate member — so a
    # shortfall is the non-retriable stale outcome instead of a conflict.
    steps = _finalize(
        KeyedWrite("delete", "Account", ({"id": 1},)),
        ACCOUNT,
        observation=VersionObservation(observed_version=3),
        concurrency="locking",
    )
    assert steps == (
        PlannedDelete(
            entity=_identity(ACCOUNT, "Account"),
            target=KeyTarget(
                key_attributes=(_attribute(ACCOUNT, "Account", "id"),), key_values=((1,),)
            ),
            concurrency=Versioned(gate=UNGATED),
            affected_rows=ExactCount(expected=1, on_shortfall=STALE_WRITE),
        ),
    )


def test_finalization_gives_an_observation_free_keyed_write_a_missing_target_shortfall() -> None:
    # An unversioned keyed write observed nothing, so a shortfall says only that
    # the addressed rows are not there. The policy is carried, not yet enforced.
    steps = _finalize(KeyedWrite("delete", "Wallet", ({"id": 1}, {"id": 2})), WALLET)
    assert steps is not None
    (step,) = steps
    assert isinstance(step, PlannedDelete)
    assert step.concurrency == UNVERSIONED
    assert step.affected_rows == ExactCount(expected=2, on_shortfall=MISSING_TARGET)


def test_finalization_gives_a_readless_predicate_write_an_unbounded_expectation() -> None:
    # A readless predicate write matching zero rows succeeds (`m-batch-write`),
    # which is what an unbounded expected effect says; it carries the typed
    # predicate and nothing else.
    predicate = oa.Comparison(op="lessThan", attr="Wallet.balance", value=200.00)
    steps = _finalize(PredicateWrite("delete", PredicateSelection("Wallet", predicate)), WALLET)
    assert steps is not None
    (step,) = steps
    assert isinstance(step, PlannedDelete)
    assert step.target == PredicateTarget(predicate=predicate)
    assert step.affected_rows == ANY_COUNT


def test_a_predicate_verb_with_no_readless_template_is_refused() -> None:
    # `terminate` and the `*Until` forms name a milestone, and every temporal
    # target materializes to keyed writes at buffer time, so no readless
    # statement shape exists for one — refused rather than settled into a step
    # no statement could render.
    with pytest.raises(WritePlanningError, match="names a milestone"):
        _finalize(PredicateWrite("terminate", PredicateSelection("Wallet", oa.All())), WALLET)


def test_a_keyed_write_row_omitting_its_primary_key_addresses_nothing() -> None:
    # Refused where the target is settled, rather than lowered into an identity
    # predicate whose bind was never supplied.
    with pytest.raises(WritePlanningError, match="omits the primary-key member"):
        _finalize(KeyedWrite("delete", "Wallet", ({"owner": "Mira"},)), WALLET)


def test_finalization_classifies_a_registry_advance_into_a_generated_value() -> None:
    # The `increment` marker is the update-position `m-pk-gen` allocation: the
    # database computes the new value from the row being written, so the settled
    # assignment names the allocation rather than a literal to bind.
    steps = _finalize(
        KeyedWrite("update", "PkSequence", ({"name": "badge_seq", "nextVal": {"increment": 3}},)),
        PK_SEQUENCE,
    )
    assert steps is not None
    (step,) = steps
    assert isinstance(step, PlannedUpdate)
    assert step.assignments.attributes[
        _attribute(PK_SEQUENCE, "PkSequence", "nextVal")
    ] == SelfIncrement(amount=3)


def test_step_lowering_reads_column_participation_and_order_from_the_layout() -> None:
    # Built by hand, with no instruction and no finalization behind it: the
    # emitted column list is the target's Table Layout slot selection filtered to
    # the step's own members, in slot order — never the row's member order.
    step = PlannedInsert(
        entity=_identity(ORDERS, "OrderItem"),
        entries=(
            InsertEntry(
                row=PlannedRow(
                    attributes={
                        _attribute(ORDERS, "OrderItem", "quantity"): 3,
                        _attribute(ORDERS, "OrderItem", "id"): 200,
                        _attribute(ORDERS, "OrderItem", "orderId"): 100,
                    }
                ),
                origin=NEW_LINEAGE,
            ),
        ),
    )
    statement = lower_step(step, models.accepted_model(ORDERS), POSTGRES)
    assert statement.sql == "insert into order_item(id, order_id, quantity) values (?, ?, ?)"
    assert statement.binds == (200, 100, 3)


def test_step_lowering_derives_the_table_per_hierarchy_tag_no_entry_names() -> None:
    # The tag is a layout fact, so it lands at its own slot in every value tuple
    # while no entry carries it — the one cell lowering adds rather than reads.
    row = PlannedRow(
        attributes={
            _attribute(PAYMENT, "CardPayment", "id"): 1,
            _attribute(PAYMENT, "CardPayment", "amount"): 10.00,
            _attribute(PAYMENT, "CardPayment", "cardNetwork"): "Visa",
        }
    )
    step = PlannedInsert(
        entity=_identity(PAYMENT, "CardPayment"),
        entries=(InsertEntry(row=row, origin=NEW_LINEAGE),),
    )
    statement = lower_step(step, models.accepted_model(PAYMENT), POSTGRES)
    assert (
        statement.sql == "insert into payment(id, kind, amount, card_network) values (?, ?, ?, ?)"
    )
    assert statement.binds == (1, "card", 10.00, "Visa")


# No corpus model declares a top-level `many` occurrence — every one of them nests a
# `many` inside a `one`, where the codec composes the array while building the outer
# document. Here the array IS the column, so the cell has to be composed by the
# lowering itself, which is what this synthetic owner isolates.
_CRATE = identity("Crate")
_CRATE_MODEL = form_metamodel(
    source(
        Declaration(
            identity=_CRATE,
            container=CoreTable("crate"),
            attributes=(key(_CRATE), attribute(_CRATE, "note", type=STRING)),
            value_objects=(
                ValueObjectOccurrenceDeclaration(
                    name="labels",
                    storage=CoreColumn("labels"),
                    multiplicity=Multiplicity.MANY,
                    shape=ValueObjectShapeDeclaration(
                        key=ValueObjectShapeKey(),
                        attributes=(ValueObjectAttributeDeclaration("text", type=STRING),),
                    ),
                ),
            ),
        )
    )
)
_CRATE_ID = AttributeIdentity(_CRATE, "id")
_CRATE_NOTE = AttributeIdentity(_CRATE, "note")


def test_an_insert_binds_the_empty_array_for_a_many_occurrence_the_row_never_names() -> None:
    # Absence and `[]` are one logical zero state, so the occurrence's own `NOT NULL`
    # column still binds — the empty array the codec composes, never a skipped column
    # (m-value-object "Writing").
    step = PlannedInsert(
        entity=_CRATE,
        entries=(InsertEntry(row=PlannedRow(attributes={_CRATE_ID: 7}), origin=NEW_LINEAGE),),
    )
    statement = lower_step(step, _CRATE_MODEL, POSTGRES)
    assert statement.sql == "insert into crate(id, labels) values (?, ?)"
    assert statement.binds == (7, JsonDocument([]))


def test_an_update_leaves_a_many_occurrence_its_assignments_never_name_alone() -> None:
    # The zero state is what an opening statement writes, not what a revising one
    # imposes: a patch touches only what it assigns, so an unnamed occurrence keeps
    # whatever the stored row holds.
    step = PlannedUpdate(
        entity=_CRATE,
        target=KeyTarget(key_attributes=(_CRATE_ID,), key_values=((7,),)),
        assignments=PlannedAssignments(attributes={_CRATE_NOTE: "fragile"}),
        concurrency=UNVERSIONED,
        affected_rows=ExactCount(expected=1, on_shortfall=MISSING_TARGET),
    )
    statement = lower_step(step, _CRATE_MODEL, POSTGRES)
    assert statement.sql == "update crate set note = ? where id = ?"
    assert statement.binds == ("fragile", 7)


def test_step_lowering_refuses_a_multi_entry_generated_value() -> None:
    # A generated value folds into the statement's own SELECT rather than
    # binding, and one such statement carries exactly one row — so a step
    # holding several is refused instead of rendered as a value list that could
    # not express it. Batch grouping never produces one (a pk-gen-managed target
    # does not collapse), so this is a hand-built shape.
    row = PlannedRow(attributes={_attribute(PK_MAX, "Attendee", "id"): MAX_PLUS_ONE})
    step = PlannedInsert(
        entity=_identity(PK_MAX, "Attendee"),
        entries=(
            InsertEntry(row=row, origin=NEW_LINEAGE),
            InsertEntry(row=row, origin=NEW_LINEAGE),
        ),
    )
    with pytest.raises(WriteLoweringError, match="one row at a time"):
        lower_step(step, models.accepted_model(PK_MAX), POSTGRES)
