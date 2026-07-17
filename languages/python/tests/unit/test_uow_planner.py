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
from parallax.core import batch_write, op_algebra
from parallax.core.descriptor import Attribute, Entity, Metamodel, Relationship
from parallax.core.unit_work import (
    AtomicUnit,
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
_PAYMENT = _MODELS["payment"]
_PK_MAX = _MODELS["pk-max"]
_WALLET = _MODELS["wallet"]

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


def test_object_key_resolves_the_family_effective_primary_key() -> None:
    # `CardPayment`'s own compiled record carries no `id` attribute at all (it
    # is declared on the family root `Payment` alone, m-inheritance "Inherited
    # members") -- a bare `Entity.primary_key` view would wrongly see no key,
    # making every inheritance-family keyed write unidentifiable (COR-3 Phase
    # 8 increment 3).
    key = object_key(KeyedWrite("update", "CardPayment", ({"id": 1, "amount": 5.00},)), _PAYMENT)
    assert key == ("CardPayment", (("id", 1),))


def test_object_key_is_none_for_a_marker_shaped_primary_key_value() -> None:
    # A pk-gen `max` insert's row carries a DB-computed marker for the id, not
    # a real value (`{computed: "maxPlusOne"}`, `m-pk-gen`): it has no
    # coalescing identity, exactly like an absent pk (kills the planner's own
    # `TypeError: unhashable type: 'dict'` crash, COR-3 Phase 8 increment 3).
    marker_insert = KeyedWrite(
        "insert", "Attendee", ({"id": {"computed": "maxPlusOne"}, "name": "Ada"},)
    )
    assert object_key(marker_insert, _PK_MAX) is None
    # And it must not crash the planner stages that coalesce/attach on it.
    plan = plan_flush([marker_insert], {}, None, _PK_MAX)
    assert len(plan.writes) == 1
    assert plan.writes[0].observation is None


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


# --------------------------------------------------------------------------- #
# Affected-rows expectation (m-opt-lock, COR-3 Phase 8 increment 3).           #
# --------------------------------------------------------------------------- #
def test_expected_affected_is_one_for_a_versioned_update_carrying_an_observation() -> None:
    update = KeyedWrite("update", "Account", ({"id": 1, "balance": 0.00},))
    key = object_key(update, _ACCOUNT)
    assert key is not None
    plan = plan_flush([update], {key: Observation(version=3)}, None, _ACCOUNT)
    assert plan.writes[0].expected_affected == 1


def test_expected_affected_is_one_for_a_versioned_delete_carrying_an_observation() -> None:
    delete = KeyedWrite("delete", "Account", ({"id": 1},))
    key = object_key(delete, _ACCOUNT)
    assert key is not None
    plan = plan_flush([delete], {key: Observation(version=3)}, None, _ACCOUNT)
    assert plan.writes[0].expected_affected == 1


def test_expected_affected_is_none_without_a_recorded_observation() -> None:
    update = KeyedWrite("update", "Account", ({"id": 1, "balance": 0.00},))
    plan = plan_flush([update], {}, None, _ACCOUNT)
    assert plan.writes[0].expected_affected is None


def test_expected_affected_is_none_for_an_insert_even_with_a_recorded_observation() -> None:
    # An observation is only ever attached (and only ever significant) for a
    # keyed update/delete; a matching insert -- structurally impossible since
    # `object_key` never resolves an insert against a PRE-EXISTING observation
    # in practice -- still carries no expectation defensively.
    insert = KeyedWrite("insert", "Account", ({"id": 1, "owner": "Ada", "balance": 0.00},))
    key = object_key(insert, _ACCOUNT)
    assert key is not None
    plan = plan_flush([insert], {key: Observation(version=3)}, None, _ACCOUNT)
    assert plan.writes[0].expected_affected is None


# --------------------------------------------------------------------------- #
# Collapse (m-batch-write's injected vocabulary, COR-3 Phase 8 increment 5).   #
# --------------------------------------------------------------------------- #
def test_collapse_is_a_noop_when_no_policy_is_injected() -> None:
    buffer = [
        KeyedWrite("insert", "Wallet", ({"id": 1, "owner": "Ada", "balance": 1.00},)),
        KeyedWrite("insert", "Wallet", ({"id": 2, "owner": "Bo", "balance": 2.00},)),
    ]
    plan = plan_flush(buffer, {}, None, _WALLET)  # no `collapse=` kwarg at all
    assert len(plan.writes) == 2


def test_collapse_merges_adjacent_same_entity_same_mutation_inserts() -> None:
    buffer = [
        KeyedWrite("insert", "Wallet", ({"id": 1, "owner": "Ada", "balance": 1.00},)),
        KeyedWrite("insert", "Wallet", ({"id": 2, "owner": "Bo", "balance": 2.00},)),
        KeyedWrite("insert", "Wallet", ({"id": 3, "owner": "Cy", "balance": 3.00},)),
    ]
    plan = plan_flush(buffer, {}, None, _WALLET, collapse=batch_write.collapses)
    assert len(plan.writes) == 1
    only = plan.writes[0].instruction
    assert isinstance(only, KeyedWrite)
    assert [dict(row) for row in only.rows] == [
        {"id": 1, "owner": "Ada", "balance": 1.00},
        {"id": 2, "owner": "Bo", "balance": 2.00},
        {"id": 3, "owner": "Cy", "balance": 3.00},
    ]


def test_collapse_merges_uniform_updates_but_not_a_lone_row() -> None:
    buffer = [KeyedWrite("update", "Wallet", ({"id": 1, "balance": 5.00},))]
    plan = plan_flush(buffer, {}, None, _WALLET, collapse=batch_write.collapses)
    assert len(plan.writes) == 1
    assert isinstance(plan.writes[0].instruction, KeyedWrite)
    assert len(plan.writes[0].instruction.rows) == 1  # a single row is never a "run"


def test_collapse_declines_a_non_uniform_update_run_leaving_rows_separate() -> None:
    buffer = [
        KeyedWrite("update", "Wallet", ({"id": 1, "balance": 111.00},)),
        KeyedWrite("update", "Wallet", ({"id": 2, "balance": 222.00},)),
    ]
    plan = plan_flush(buffer, {}, None, _WALLET, collapse=batch_write.collapses)
    assert len(plan.writes) == 2  # `batch_write.update_collapses` declines: not uniform


def test_collapse_never_regroups_across_an_intervening_different_entity() -> None:
    buffer = [
        KeyedWrite("insert", "Wallet", ({"id": 1, "owner": "Ada", "balance": 1.00},)),
        KeyedWrite("insert", "Person", ({"id": 99},)),
        KeyedWrite("insert", "Wallet", ({"id": 2, "owner": "Bo", "balance": 2.00},)),
    ]
    meta = Metamodel(entities=(*_WALLET.entities, *_PERSON.entities))
    plan = plan_flush(buffer, {}, None, meta, collapse=batch_write.collapses)
    # FK-order groups all inserts together, but the two Wallet rows were NEVER
    # adjacent in BUFFER order (Person interrupted the run), so they stay two
    # separate single-row instructions rather than merging into one.
    wallet_writes = [
        p
        for p in plan.writes
        if isinstance(p.instruction, KeyedWrite) and p.instruction.entity == "Wallet"
    ]
    assert len(wallet_writes) == 2


def test_collapse_never_merges_a_row_carrying_a_recorded_observation() -> None:
    # A row explicitly signalled as separately-observed (e.g. an engine
    # `observedVersion` control key, or a real transaction-scoped
    # `uow.observe`) is never a merge candidate: a multi-row instruction has
    # no way to carry a per-row observation forward.
    row1 = KeyedWrite("update", "Wallet", ({"id": 1, "balance": 5.00},))
    row2 = KeyedWrite("update", "Wallet", ({"id": 2, "balance": 5.00},))
    key1 = object_key(row1, _WALLET)
    assert key1 is not None
    plan = plan_flush(
        [row1, row2], {key1: Observation(version=1)}, None, _WALLET, collapse=batch_write.collapses
    )
    # Even though the values are uniform (otherwise collapse-eligible), row1's
    # recorded observation forces both rows to stay separate.
    assert len(plan.writes) == 2


def test_collapse_never_touches_a_predicate_write() -> None:
    predicate = PredicateWrite(
        "delete", WriteTarget("Wallet", op_algebra.Comparison("lessThan", "Wallet.balance", 1.0))
    )
    plan = plan_flush([predicate], {}, None, _WALLET, collapse=batch_write.collapses)
    assert plan.writes[0].instruction is predicate


# --------------------------------------------------------------------------- #
# AtomicUnit (a materialized predicate write's planned unit, COR-3 Phase 8    #
# increment 5, `m-unit-work` "Materialized predicate writes are an atomic     #
# planned unit"): exempt from coalescing and from collapse; FK-order moves it #
# as ONE block, its internal row order untouched; flattened to a plain,       #
# per-row `PlannedWrite` sequence by the time `plan_flush` returns.            #
# --------------------------------------------------------------------------- #
def test_atomic_unit_flattens_to_its_member_writes_in_order() -> None:
    unit = AtomicUnit(
        writes=(
            KeyedWrite("update", "Account", ({"id": 1, "balance": 10.00},)),
            KeyedWrite("update", "Account", ({"id": 2, "balance": 20.00},)),
        )
    )
    plan = plan_flush([unit], {}, None, _ACCOUNT)
    assert len(plan.writes) == 2
    assert _rows(plan) == [{"id": 1, "balance": 10.00}, {"id": 2, "balance": 20.00}]


def test_atomic_unit_is_exempt_from_same_object_coalescing() -> None:
    # An AtomicUnit's own row is never folded with an unrelated buffered
    # insert of the SAME object identity — it passes through coalesce opaque.
    insert = KeyedWrite("insert", "Account", ({"id": 1, "owner": "Ada", "balance": 1.00},))
    unit = AtomicUnit(writes=(KeyedWrite("update", "Account", ({"id": 1, "balance": 2.00},)),))
    plan = plan_flush([insert, unit], {}, None, _ACCOUNT)
    assert len(plan.writes) == 2
    mutations = [
        planned.instruction.mutation
        for planned in plan.writes
        if isinstance(planned.instruction, KeyedWrite)
    ]
    assert mutations == ["insert", "update"]  # NOT coalesced into one insert


def test_atomic_unit_is_exempt_from_collapse() -> None:
    # An AtomicUnit's OWN member writes never re-collapse into a multi-row
    # instruction, even when they would otherwise be eligible (adjacent,
    # same entity/mutation, uniform values).
    unit = AtomicUnit(
        writes=(
            KeyedWrite("update", "Wallet", ({"id": 1, "balance": 5.00},)),
            KeyedWrite("update", "Wallet", ({"id": 2, "balance": 5.00},)),
        )
    )
    plan = plan_flush([unit], {}, None, _WALLET, collapse=batch_write.collapses)
    assert len(plan.writes) == 2


def test_atomic_unit_moves_as_one_block_under_fk_ordering() -> None:
    # The unit's own rows (Order, an FK-referenced parent's later rank) stay
    # ADJACENT and in their OWN resolved-row order, moved as a whole relative
    # to the OTHER buffered instruction (an OrderItem insert, a child) — FK
    # order alone would otherwise put child-then-parent updates in a
    # DIFFERENT relative position than the unit's own internal order.
    unit = AtomicUnit(
        writes=(
            KeyedWrite("update", "Order", ({"id": 2, "name": "Y"},)),
            KeyedWrite("update", "Order", ({"id": 1, "name": "X"},)),
        )
    )
    other = KeyedWrite("insert", "OrderItem", ({"id": 10, "orderId": 1, "sku": "A", "qty": 1},))
    plan = plan_flush([unit, other], {}, None, _ORDERS)
    kinds = [
        (
            planned.instruction.mutation,
            planned.instruction.entity if isinstance(planned.instruction, KeyedWrite) else None,
            dict(planned.instruction.rows[0]).get("id")
            if isinstance(planned.instruction, KeyedWrite)
            else None,
        )
        for planned in plan.writes
    ]
    # inserts (OrderItem) before updates (Order, x2) — the canonical
    # INSERT -> UPDATE -> DELETE order; the unit's OWN two rows stay adjacent
    # and in their OWN authored order (2 then 1), never re-sorted by id.
    assert kinds == [
        ("insert", "OrderItem", 10),
        ("update", "Order", 2),
        ("update", "Order", 1),
    ]


def test_atomic_unit_member_observations_attach_individually() -> None:
    row1 = KeyedWrite("update", "Account", ({"id": 1, "balance": 1.00},))
    row2 = KeyedWrite("update", "Account", ({"id": 2, "balance": 2.00},))
    key1 = object_key(row1, _ACCOUNT)
    key2 = object_key(row2, _ACCOUNT)
    assert key1 is not None and key2 is not None
    unit = AtomicUnit(writes=(row1, row2))
    observations = {key1: Observation(version=1), key2: Observation(version=5)}
    plan = plan_flush([unit], observations, None, _ACCOUNT)
    versions = {
        dict(planned.instruction.rows[0])["id"]: (
            planned.observation.version if planned.observation is not None else None
        )
        for planned in plan.writes
        if isinstance(planned.instruction, KeyedWrite)
    }
    assert versions == {1: 1, 2: 5}
    assert all(planned.expected_affected == 1 for planned in plan.writes)
