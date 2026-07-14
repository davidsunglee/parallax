"""Pure flush-planner unit tests (m-unit-work, Docker-free).

Exercises the three planner stages independently of the compile/run sweeps and of
any SQL lowering (the planner emits a neutral plan, never DML): same-transaction
coalescing (insert-then-update in place per temporal flavor; insert-then-delete
cancellation), foreign-key ordering over the descriptor graph, empty-change-set
elision, object identity, and the neutral observation binding.
"""

from __future__ import annotations

import pytest

from parallax.conformance import models
from parallax.core import op_algebra
from parallax.core.descriptor import Attribute, Entity, Metamodel, Relationship
from parallax.core.unit_work import (
    FlushPlan,
    KeyedWrite,
    Observation,
    PredicateWrite,
    WriteTarget,
    object_key,
    plan_flush,
)

pytestmark = pytest.mark.unit

_MODELS = models.load_models()
_ACCOUNT = _MODELS["account"]
_BALANCE = _MODELS["balance"]
_POSITION = _MODELS["position"]
_ORDERS = _MODELS["orders"]
_PERSON = _MODELS["person"]

_B1 = "2024-01-01T00:00:00+00:00"


def _rows(plan: FlushPlan) -> list[dict[str, object]]:
    out: list[dict[str, object]] = []
    for planned in plan.writes:
        assert isinstance(planned.instruction, KeyedWrite)
        out.append(dict(planned.instruction.rows[0]))
    return out


# --------------------------------------------------------------------------- #
# Coalesce.                                                                    #
# --------------------------------------------------------------------------- #
def test_nontemporal_insert_then_update_coalesces_to_one_insert() -> None:
    insert = KeyedWrite("insert", "Account", ({"id": 9, "owner": "Noether", "balance": 5.00},))
    update = KeyedWrite("update", "Account", ({"id": 9, "balance": 99.00},))
    plan = plan_flush([insert, update], {}, None, _ACCOUNT)
    assert len(plan.writes) == 1
    only = plan.writes[0].instruction
    assert isinstance(only, KeyedWrite)
    assert only.mutation == "insert"  # a single INSERT with final values, never INSERT + UPDATE
    assert dict(only.rows[0]) == {"id": 9, "owner": "Noether", "balance": 99.00}


def test_audit_insert_then_update_coalesces_in_place() -> None:
    insert = KeyedWrite("insert", "Balance", ({"id": 9, "acctNum": "D", "value": 100.00},))
    update = KeyedWrite("update", "Balance", ({"id": 9, "value": 150.00},))
    plan = plan_flush([insert, update], {}, None, _BALANCE)
    assert _rows(plan) == [{"id": 9, "acctNum": "D", "value": 150.00}]
    assert plan.writes[0].instruction.mutation == "insert"  # one current milestone, no close


def test_bitemporal_insert_then_update_keeps_the_business_bound() -> None:
    insert = KeyedWrite(
        "insert", "Position", ({"id": 9, "acctNum": "D", "value": 100.00},), business_from=_B1
    )
    update = KeyedWrite("update", "Position", ({"id": 9, "value": 150.00},))
    plan = plan_flush([insert, update], {}, None, _POSITION)
    only = plan.writes[0].instruction
    assert isinstance(only, KeyedWrite)
    assert dict(only.rows[0]) == {"id": 9, "acctNum": "D", "value": 150.00}
    assert only.business_from == _B1  # one fully-current rectangle, no head/tail split


def test_insert_then_delete_cancels_to_no_dml() -> None:
    insert = KeyedWrite("insert", "Account", ({"id": 9, "owner": "Noether", "balance": 5.00},))
    delete = KeyedWrite("delete", "Account", ({"id": 9},))
    plan = plan_flush([insert, delete], {}, None, _ACCOUNT)
    assert plan.writes == ()  # both annihilate — the net-zero elision across two verbs


def test_insert_then_multiple_updates_fold_into_one_insert() -> None:
    insert = KeyedWrite("insert", "Account", ({"id": 9, "owner": "Noether", "balance": 5.00},))
    update1 = KeyedWrite("update", "Account", ({"id": 9, "balance": 50.00},))
    update2 = KeyedWrite("update", "Account", ({"id": 9, "owner": "Markov"},))
    plan = plan_flush([insert, update1, update2], {}, None, _ACCOUNT)
    assert _rows(plan) == [{"id": 9, "owner": "Markov", "balance": 50.00}]


def test_update_of_a_row_not_inserted_this_transaction_is_not_coalesced() -> None:
    update = KeyedWrite("update", "Account", ({"id": 1, "balance": 0.00},))
    plan = plan_flush([update], {}, None, _ACCOUNT)
    assert len(plan.writes) == 1
    assert plan.writes[0].instruction.mutation == "update"


def test_delete_of_a_row_not_inserted_this_transaction_is_not_coalesced() -> None:
    delete = KeyedWrite("delete", "Account", ({"id": 1},))
    plan = plan_flush([delete], {}, None, _ACCOUNT)
    assert len(plan.writes) == 1
    assert plan.writes[0].instruction.mutation == "delete"


def test_multi_row_and_pk_generated_and_predicate_writes_do_not_coalesce() -> None:
    multi = KeyedWrite(
        "insert", "Account", ({"id": 8, "balance": 1.00}, {"id": 9, "balance": 2.00})
    )
    pk_gen = KeyedWrite("insert", "Account", ({"owner": "Ada", "balance": 1.00},))  # no PK in row
    predicate = PredicateWrite(
        "delete", WriteTarget("Account", op_algebra.Comparison("eq", "Account.id", 1))
    )
    plan = plan_flush([multi, pk_gen, predicate], {}, None, _ACCOUNT)
    # None is a single-object keyed write, so none coalesces — all pass through.
    assert len(plan.writes) == 3


# --------------------------------------------------------------------------- #
# FK ordering.                                                                 #
# --------------------------------------------------------------------------- #
def _entities(plan: FlushPlan) -> list[str]:
    out: list[str] = []
    for planned in plan.writes:
        instruction = planned.instruction
        out.append(
            instruction.entity if isinstance(instruction, KeyedWrite) else instruction.target.entity
        )
    return out


def test_inserts_order_parents_before_children() -> None:
    buffer = [
        KeyedWrite("insert", "OrderStatus", ({"id": 100},)),
        KeyedWrite("insert", "OrderTag", ({"id": 1000},)),
        KeyedWrite("insert", "OrderItem", ({"id": 10},)),
        KeyedWrite("insert", "Order", ({"id": 1},)),
    ]
    plan = plan_flush(buffer, {}, None, _ORDERS)
    assert _entities(plan) == ["Order", "OrderItem", "OrderStatus", "OrderTag"]


def test_deletes_order_children_before_parents() -> None:
    buffer = [
        KeyedWrite("delete", "Order", ({"id": 1},)),
        KeyedWrite("delete", "OrderItem", ({"id": 10},)),
        KeyedWrite("delete", "OrderStatus", ({"id": 100},)),
    ]
    plan = plan_flush(buffer, {}, None, _ORDERS)
    assert _entities(plan) == ["OrderStatus", "OrderItem", "Order"]


def test_mixed_flush_is_insert_then_update_then_delete() -> None:
    buffer = [
        KeyedWrite("delete", "OrderStatus", ({"id": 100},)),
        KeyedWrite("update", "OrderItem", ({"id": 10, "quantity": 5},)),
        KeyedWrite("insert", "Order", ({"id": 2},)),
    ]
    plan = plan_flush(buffer, {}, None, _ORDERS)
    kinds = [(p.instruction.mutation, _entities(plan)[i]) for i, p in enumerate(plan.writes)]
    assert kinds == [("insert", "Order"), ("update", "OrderItem"), ("delete", "OrderStatus")]


def test_one_to_one_relationships_contribute_no_fk_edge() -> None:
    # Person <-> Passport are both one-to-one: neither the many-to-one nor the
    # one-to-many edge fires, so ranking simply keeps declaration order.
    buffer = [
        KeyedWrite("insert", "Person", ({"id": 1},)),
        KeyedWrite("insert", "Passport", ({"id": 2},)),
    ]
    plan = plan_flush(buffer, {}, None, _PERSON)
    assert _entities(plan) == ["Person", "Passport"]


def test_relationship_reaching_outside_the_model_has_no_local_order() -> None:
    widget = Entity(
        name="Widget",
        attributes=(Attribute(name="id", type="int64", column="id", primary_key=True),),
        relationships=(
            Relationship(
                name="gadget", related_entity="Gadget", cardinality="many-to-one", join="x = y"
            ),
        ),
    )
    meta = Metamodel(entities=(widget,))
    plan = plan_flush([KeyedWrite("insert", "Widget", ({"id": 1},))], {}, None, meta)
    assert _entities(plan) == ["Widget"]


# --------------------------------------------------------------------------- #
# Elision.                                                                     #
# --------------------------------------------------------------------------- #
def test_empty_change_set_update_emits_no_instruction() -> None:
    update = KeyedWrite("update", "Account", ({"id": 1},))  # only the PK: no changed field
    plan = plan_flush([update], {}, None, _ACCOUNT)
    assert plan.writes == ()


def test_nonempty_change_set_update_survives_elision() -> None:
    update = KeyedWrite("update", "Account", ({"id": 1, "balance": 7.00},))
    plan = plan_flush([update], {}, None, _ACCOUNT)
    assert len(plan.writes) == 1


def test_empty_plan_from_empty_buffer() -> None:
    assert plan_flush([], {}, None, _ACCOUNT) == FlushPlan(writes=(), tx_instant=None)


# --------------------------------------------------------------------------- #
# Object identity + observation binding.                                       #
# --------------------------------------------------------------------------- #
def test_object_key_of_a_single_row_keyed_write() -> None:
    key = object_key(KeyedWrite("update", "Account", ({"id": 1, "balance": 0},)), _ACCOUNT)
    assert key == ("Account", (("id", 1),))


def test_object_key_is_none_for_unidentifiable_writes() -> None:
    assert object_key(KeyedWrite("insert", "Account", ({"id": 1}, {"id": 2})), _ACCOUNT) is None
    assert object_key(KeyedWrite("insert", "Account", ({"owner": "Ada"},)), _ACCOUNT) is None
    predicate = PredicateWrite("delete", WriteTarget("Account", op_algebra.All()))
    assert object_key(predicate, _ACCOUNT) is None


def test_object_key_is_none_for_a_keyless_entity() -> None:
    blob = Entity(name="Blob", attributes=(Attribute(name="data", type="string", column="data"),))
    meta = Metamodel(entities=(blob,))
    assert object_key(KeyedWrite("delete", "Blob", ({"data": "x"},)), meta) is None


def test_recorded_observation_binds_to_its_planned_write() -> None:
    update = KeyedWrite("update", "Account", ({"id": 1, "balance": 0.00},))
    other = KeyedWrite("update", "Account", ({"id": 2, "balance": 0.00},))
    key = object_key(update, _ACCOUNT)
    assert key is not None
    observation = Observation(version=3)
    plan = plan_flush([update, other], {key: observation}, None, _ACCOUNT)
    bound: dict[object, Observation | None] = {}
    for planned in plan.writes:
        instruction = planned.instruction
        assert isinstance(instruction, KeyedWrite)
        bound[dict(instruction.rows[0])["id"]] = planned.observation
    assert bound[1] == observation  # id 1 carries the recorded observation
    assert bound[2] is None  # id 2 has none


def test_tx_instant_flows_through_as_plan_context() -> None:
    plan = plan_flush(
        [KeyedWrite("insert", "Account", ({"id": 1},))], {}, "2024-06-01T00:00:00+00:00", _ACCOUNT
    )
    assert plan.tx_instant == "2024-06-01T00:00:00+00:00"
