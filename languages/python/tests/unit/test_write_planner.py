"""``WritePlanner.plan`` — the primary neutral seam (m-unit-work, Docker-free).

``WritePlanner.plan(PlanningRequest) -> WritePlan`` is the entire
caller-visible planning surface: no caller sequences coalescing, batching,
ordering, temporal expansion, observation binding, instant acquisition, or
provenance decoration by hand. These tests drive it directly — through the
SAME production wiring ``parallax.snapshot.handle.build_write_planner``
builds — asserting complete ``PlannedWrite`` shapes and plan-wide ordering,
never a private stage function: same-transaction coalescing (insert-then-update
in place per temporal flavor; insert-then-delete cancellation), dependency
ordering over the descriptor graph and the readless-predicate-write barriers
that partition it, empty-change-set elision, batching (`m-batch-write`),
Materialized Write Group settlement, optimistic-mode gates, and temporal
in-place adjacency.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Sequence

import pytest
from _corpus_identity_support import corpus_object_key
from _metamodel_support import Declaration, attribute, identity, key, source

from _support.clock_probes import CountingClock, inert_instant, instant_at
from _support.planner_probes import TEST_SUBJECT_IDENTITY
from parallax.conformance import models
from parallax.core import op_algebra, opt_lock
from parallax.core._formation_profile import form_metamodel
from parallax.core.metamodel import (
    AttributeIdentity,
    AttributeReference,
    Cardinality,
    Metamodel,
    RelationshipIdentity,
    RelativeEntityReference,
    Table,
    UnresolvedDefiningRelationshipDeclaration,
    UnresolvedRelationshipJoin,
)
from parallax.core.unit_work import (
    ANY_COUNT,
    LATEST_PINNED,
    MAX_PLUS_ONE,
    MISSING_TARGET,
    OPTIMISTIC_CONFLICT,
    STALE_WRITE,
    UNGATED,
    BufferItem,
    ChunkedColumnBuilder,
    Concurrency,
    ExactCount,
    KeyedWrite,
    KeyTarget,
    MaterializedWriteGroup,
    ObjectKey,
    PlannedClose,
    PlannedDelete,
    PlannedInsert,
    PlannedRow,
    PlannedUpdate,
    PlannedWrite,
    PlanningRequest,
    PredecessorRow,
    PredicateMutation,
    PredicateSelection,
    PredicateTarget,
    PredicateWrite,
    TemporalObservation,
    TransactionInstant,
    VersionColumns,
    Versioned,
    VersionGate,
    VersionObservation,
    WriteAssignment,
    WriteObservation,
    WritePlan,
    WritePlanningError,
    object_key,
    whole,
)
from parallax.descriptor._records import Metamodel as DescriptorMetamodel
from parallax.snapshot.handle import build_write_planner

_MODELS = models.load_models()
_ACCOUNT = models.accepted_model(_MODELS["account"])
_BALANCE = models.accepted_model(_MODELS["balance"])
_POSITION = models.accepted_model(_MODELS["position"])
_ORDERS = models.accepted_model(_MODELS["orders"])
_PERSON = models.accepted_model(_MODELS["person"])
_PAYMENT = models.accepted_model(_MODELS["payment"])
_PK_MAX = models.accepted_model(_MODELS["pk-max"])
_WALLET = models.accepted_model(_MODELS["wallet"])

_B1 = "2024-01-01T00:00:00+00:00"

# The planner threads its Transaction Instant through untouched to whichever
# stage first needs it, so every non-temporal test below shares one uncaptured
# holder rather than pinning an instant it would never read.
_INSTANT = inert_instant()


def _plan(
    buffer: list[BufferItem],
    model: Metamodel,
    *,
    observations: dict[ObjectKey, WriteObservation] | None = None,
    concurrency: Concurrency = "locking",
    tx_instant: TransactionInstant | None = None,
) -> WritePlan:
    return build_write_planner(model).plan(
        PlanningRequest(
            subject_identity=TEST_SUBJECT_IDENTITY,
            transaction_instant=tx_instant if tx_instant is not None else _INSTANT,
            concurrency=concurrency,
            buffered_writes=buffer,
            observations=observations or {},
        )
    )


def _row_values(row: PlannedRow) -> dict[str, object]:
    values: dict[str, object] = {ident.name: value for ident, value in row.attributes.items()}
    for ident, value in row.value_objects.items():
        values[ident.path[-1]] = value
    return values


def _insert_rows(step: PlannedWrite) -> list[dict[str, object]]:
    assert isinstance(step, PlannedInsert)
    return [_row_values(entry.row) for entry in step.entries]


def _step_entity(step: PlannedWrite) -> str:
    return step.entity.name


def _step_mutation(step: PlannedWrite) -> str:
    if isinstance(step, PlannedInsert):
        return "insert"
    if isinstance(step, PlannedUpdate):
        return "update"
    if isinstance(step, PlannedClose):
        return "close"
    return "delete"


def _entities(plan: WritePlan) -> list[str]:
    return [_step_entity(step) for step in plan.steps]


def _key_values(step: PlannedUpdate | PlannedDelete) -> tuple[tuple[object, ...], ...]:
    assert isinstance(step.target, KeyTarget)
    return step.target.key_values


def _single_key(step: PlannedUpdate | PlannedDelete) -> object:
    (values,) = _key_values(step)
    (value,) = values
    return value


def _version_group(
    entity: str,
    mutation: PredicateMutation,
    key_name: str,
    rows: Sequence[tuple[object, int]],
    assignments: Sequence[WriteAssignment] = (),
) -> MaterializedWriteGroup:
    """A minimal Materialized Write Group for planner-seam tests.

    ``rows`` is ``(key value, observed version)`` per resolved row; every row
    shares ``assignments`` uniformly, the real shape a materializing predicate
    write settles to (`m-unit-work` "Materialized Write Groups") — a
    Materialized Write Group carries no per-row assigned value, only per-row
    key and observation columns.
    """
    keys: ChunkedColumnBuilder[object] = ChunkedColumnBuilder()
    versions: ChunkedColumnBuilder[int] = ChunkedColumnBuilder()
    for key_value, version in rows:
        keys.append(key_value)
        versions.append(version)
    predicate = PredicateWrite(
        mutation,
        PredicateSelection(
            entity, op_algebra.Comparison("lessThan", f"{entity}.balance", 1_000_000.0)
        ),
        assignments=tuple(assignments),
    )
    return MaterializedWriteGroup(
        mutation=predicate,
        key_attributes=(key_name,),
        key_columns=(whole(keys.build()),),
        observations=VersionColumns(versions=whole(versions.build())),
    )


def _shape(plan: WritePlan) -> list[tuple[str, str]]:
    return [(_step_mutation(step), _step_entity(step)) for step in plan.steps]


# --------------------------------------------------------------------------- #
# Coalesce (m-unit-work "Same-transaction write coalescing").                 #
# --------------------------------------------------------------------------- #
def test_nontemporal_insert_then_update_coalesces_to_one_insert() -> None:
    insert = KeyedWrite("insert", "Account", ({"id": 9, "owner": "Noether", "balance": 5.00},))
    update = KeyedWrite("update", "Account", ({"id": 9, "balance": 99.00},))
    plan = _plan([insert, update], _ACCOUNT)
    (step,) = plan.steps
    assert isinstance(step, PlannedInsert)
    (row,) = _insert_rows(step)
    # A single INSERT with final values, never INSERT + UPDATE; the framework
    # still derives the initial version onto the ONE surviving row.
    assert row["owner"] == "Noether"
    assert row["balance"] == 99.00
    assert row["version"] == 1


def test_audit_insert_then_update_coalesces_in_place() -> None:
    insert = KeyedWrite("insert", "Balance", ({"id": 9, "acctNum": "D", "value": 100.00},))
    update = KeyedWrite("update", "Balance", ({"id": 9, "value": 150.00},))
    plan = _plan([insert, update], _BALANCE, tx_instant=instant_at(_B1))
    (step,) = plan.steps
    assert isinstance(step, PlannedInsert)  # one current milestone, no close
    (row,) = _insert_rows(step)
    assert row["acctNum"] == "D"
    assert row["value"] == 150.00
    assert row["txStart"] == _B1


def test_bitemporal_insert_then_update_keeps_the_valid_time_bound() -> None:
    insert = KeyedWrite(
        "insert", "Position", ({"id": 9, "acctNum": "D", "value": 100.00},), valid_from=_B1
    )
    update = KeyedWrite("update", "Position", ({"id": 9, "value": 150.00},))
    plan = _plan([insert, update], _POSITION, tx_instant=instant_at(_B1))
    (step,) = plan.steps
    assert isinstance(step, PlannedInsert)  # one fully-current rectangle, no head/tail split
    (row,) = _insert_rows(step)
    assert row["acctNum"] == "D"
    assert row["value"] == 150.00
    assert row["validStart"] == _B1


def test_insert_then_delete_cancels_to_no_dml() -> None:
    insert = KeyedWrite("insert", "Account", ({"id": 9, "owner": "Noether", "balance": 5.00},))
    delete = KeyedWrite("delete", "Account", ({"id": 9},))
    plan = _plan([insert, delete], _ACCOUNT)
    assert len(plan.steps) == 0  # both annihilate — the net-zero elision across two verbs


def test_insert_then_multiple_updates_fold_into_one_insert() -> None:
    insert = KeyedWrite("insert", "Account", ({"id": 9, "owner": "Noether", "balance": 5.00},))
    update1 = KeyedWrite("update", "Account", ({"id": 9, "balance": 50.00},))
    update2 = KeyedWrite("update", "Account", ({"id": 9, "owner": "Markov"},))
    plan = _plan([insert, update1, update2], _ACCOUNT)
    (step,) = plan.steps
    (row,) = _insert_rows(step)
    assert row["owner"] == "Markov"
    assert row["balance"] == 50.00


def test_update_of_a_row_not_inserted_this_transaction_is_not_coalesced() -> None:
    update = KeyedWrite("update", "Wallet", ({"id": 1, "balance": 0.00},))
    plan = _plan([update], _WALLET)
    (step,) = plan.steps
    assert isinstance(step, PlannedUpdate)


def test_delete_of_a_row_not_inserted_this_transaction_is_not_coalesced() -> None:
    delete = KeyedWrite("delete", "Wallet", ({"id": 1},))
    plan = _plan([delete], _WALLET)
    (step,) = plan.steps
    assert isinstance(step, PlannedDelete)


def test_multi_row_and_unkeyed_and_predicate_writes_do_not_coalesce() -> None:
    # Wallet (unversioned, non-temporal): a readless predicate write is only
    # ever legal there, so this stays about the coalescing exemption alone.
    multi = KeyedWrite("insert", "Wallet", ({"id": 8, "balance": 1.00}, {"id": 9, "balance": 2.00}))
    unkeyed = KeyedWrite("insert", "Wallet", ({"owner": "Ada", "balance": 1.00},))  # no PK in row
    predicate = PredicateWrite(
        "delete", PredicateSelection("Wallet", op_algebra.Comparison("eq", "Wallet.id", 1))
    )
    plan = _plan([multi, unkeyed, predicate], _WALLET)
    # None is a single-object keyed write, so none coalesces — all pass through
    # (the multi-row insert is one step, `unkeyed` and the predicate one each).
    assert len(plan.steps) == 3


# --------------------------------------------------------------------------- #
# Dependency ordering (foreign-key parents-before-children).                  #
# --------------------------------------------------------------------------- #
def test_inserts_order_parents_before_children() -> None:
    buffer: list[BufferItem] = [
        KeyedWrite("insert", "OrderStatus", ({"id": 100, "orderId": 1},)),
        KeyedWrite(
            "insert", "OrderTag", ({"id": 1000, "orderId": 1, "label": "x", "priority": 1},)
        ),
        KeyedWrite("insert", "OrderItem", ({"id": 10, "orderId": 1, "sku": "A", "quantity": 1},)),
        KeyedWrite(
            "insert",
            "Order",
            ({"id": 1, "name": "N", "qty": 1, "price": 1.0, "active": True, "orderedOn": _B1},),
        ),
    ]
    plan = _plan(buffer, _ORDERS)
    assert _entities(plan) == ["Order", "OrderItem", "OrderStatus", "OrderTag"]


def test_deletes_order_children_before_parents() -> None:
    buffer: list[BufferItem] = [
        KeyedWrite("delete", "Order", ({"id": 1},)),
        KeyedWrite("delete", "OrderItem", ({"id": 10},)),
        KeyedWrite("delete", "OrderStatus", ({"id": 100},)),
    ]
    plan = _plan(buffer, _ORDERS)
    assert _entities(plan) == ["OrderStatus", "OrderItem", "Order"]


def test_mixed_flush_is_insert_then_update_then_delete() -> None:
    buffer: list[BufferItem] = [
        KeyedWrite("delete", "OrderStatus", ({"id": 100},)),
        KeyedWrite("update", "OrderItem", ({"id": 10, "quantity": 5},)),
        KeyedWrite(
            "insert",
            "Order",
            ({"id": 2, "name": "N", "qty": 1, "price": 1.0, "active": True, "orderedOn": _B1},),
        ),
    ]
    plan = _plan(buffer, _ORDERS)
    assert _shape(plan) == [
        ("insert", "Order"),
        ("update", "OrderItem"),
        ("delete", "OrderStatus"),
    ]


def test_one_to_one_relationships_contribute_no_fk_edge() -> None:
    # Person <-> Passport are both one-to-one: neither the many-to-one nor the
    # one-to-many edge fires, so ranking falls back to the accepted model's own
    # canonical Entity order.
    buffer: list[BufferItem] = [
        KeyedWrite("insert", "Person", ({"id": 1, "name": "A"},)),
        KeyedWrite("insert", "Passport", ({"id": 2, "personId": 1, "number": "X"},)),
    ]
    plan = _plan(buffer, _PERSON)
    assert _entities(plan) == ["Passport", "Person"]


def test_a_defining_many_to_one_orders_its_source_after_its_target() -> None:
    # No corpus model declares a defining `many-to-one` (each is authored from
    # the `one-to-many` side with a reverse peer), so the source-holds-the-key
    # direction is proven over a hand-built model. Canonical Entity order puts
    # `Alpha` first; the FK edge overrides it.
    parent = identity("Zeta")
    child = identity("Alpha")
    model = form_metamodel(
        source(
            Declaration(identity=parent, container=Table("zeta"), attributes=(key(parent),)),
            Declaration(
                identity=child,
                container=Table("alpha"),
                attributes=(key(child), attribute(child, "zetaId")),
                relationships=(
                    UnresolvedDefiningRelationshipDeclaration(
                        identity=RelationshipIdentity(child, "zeta"),
                        cardinality=Cardinality.MANY_TO_ONE,
                        join=UnresolvedRelationshipJoin(
                            source=AttributeIdentity(child, "zetaId"),
                            target=AttributeReference(RelativeEntityReference("Zeta"), "id"),
                        ),
                    ),
                ),
            ),
        )
    )
    buffer: list[BufferItem] = [
        KeyedWrite("insert", "Alpha", ({"id": 1, "zetaId": 2},)),
        KeyedWrite("insert", "Zeta", ({"id": 2},)),
    ]
    assert _entities(_plan(buffer, model)) == ["Zeta", "Alpha"]


def test_an_instruction_naming_an_undeclared_entity_is_a_planning_error() -> None:
    # Every settled step needs its Entity resolved (`_require_entity`), so an
    # instruction naming one the accepted Metamodel does not declare is refused
    # as a caller wiring defect during planning — never silently ranked first
    # by the ordering stage's own defensive fallback and lowered anyway.
    buffer: list[BufferItem] = [
        KeyedWrite("insert", "OrderItem", ({"id": 10, "orderId": 1, "sku": "A", "quantity": 1},)),
        KeyedWrite("insert", "Gadget", ({"id": 1, "name": "G"},)),
    ]
    with pytest.raises(WritePlanningError, match="Gadget"):
        _plan(buffer, _ORDERS)


def test_an_undeclared_entitys_keyed_update_survives_elision_to_the_same_refusal() -> None:
    # An undeclared entity is unresolvable for elision (its effective change set
    # cannot be proven empty), so a keyed update naming one is never silently
    # dropped as a no-op — it survives to the SAME planning refusal an insert of
    # an undeclared entity reaches. Isolated from the sibling test above (which
    # pairs an undeclared insert with a resolvable one): pairing this update with
    # any undeclared insert of the same entity would let the insert's own
    # refusal fire first and leave elision's behavior unobserved.
    buffer: list[BufferItem] = [KeyedWrite("update", "Gadget", ({"id": 1},))]
    with pytest.raises(WritePlanningError, match="Gadget"):
        _plan(buffer, _ORDERS)


# --------------------------------------------------------------------------- #
# Readless predicate-write ordering barriers (ADR 0043).                      #
# --------------------------------------------------------------------------- #
# One assignable string Attribute per Orders entity this barrier suite
# targets, since each declares a different member name.
_ASSIGNABLE_MEMBER = {"Order": "name", "OrderItem": "sku", "OrderTag": "label"}


def _predicate_update(entity: str) -> PredicateWrite:
    member = _ASSIGNABLE_MEMBER[entity]
    return PredicateWrite(
        "update",
        PredicateSelection(entity, op_algebra.Comparison("eq", f"{entity}.id", 1)),
        assignments=(WriteAssignment(f"{entity}.{member}", "Z"),),
    )


def test_no_keyed_write_crosses_a_readless_predicate_write_in_either_direction() -> None:
    # The bucket sort alone would hoist the trailing insert to the front and
    # push the leading delete to the back, moving BOTH across the predicate
    # write — a readless predicate does not reveal which rows it matches, so
    # either move could change what it writes. The barrier pins all three.
    buffer: list[BufferItem] = [
        KeyedWrite("delete", "OrderItem", ({"id": 10},)),
        _predicate_update("Order"),
        KeyedWrite(
            "insert",
            "Order",
            ({"id": 2, "name": "N", "qty": 1, "price": 1.0, "active": True, "orderedOn": _B1},),
        ),
    ]
    plan = _plan(buffer, _ORDERS)
    assert _shape(plan) == [
        ("delete", "OrderItem"),
        ("update", "Order"),
        ("insert", "Order"),
    ]
    predicate_step = plan.steps[1]
    assert isinstance(predicate_step, PlannedUpdate)
    assert predicate_step.target == PredicateTarget(
        predicate=op_algebra.Comparison("eq", "Order.id", 1)
    )


def test_fk_ordering_still_applies_independently_within_each_barrier_region() -> None:
    # Ordering is unconstrained WITHIN a region: each side is bucketed and
    # ordered on its own (parents before children), and the two sides never
    # see each other's items.
    buffer: list[BufferItem] = [
        KeyedWrite("insert", "OrderItem", ({"id": 10, "orderId": 1, "sku": "A", "quantity": 1},)),
        KeyedWrite(
            "insert",
            "Order",
            ({"id": 1, "name": "N", "qty": 1, "price": 1.0, "active": True, "orderedOn": _B1},),
        ),
        _predicate_update("OrderTag"),
        KeyedWrite(
            "insert", "OrderTag", ({"id": 1000, "orderId": 1, "label": "x", "priority": 1},)
        ),
        KeyedWrite("insert", "OrderStatus", ({"id": 100, "orderId": 1},)),
    ]
    plan = _plan(buffer, _ORDERS)
    assert _entities(plan) == ["Order", "OrderItem", "OrderTag", "OrderStatus", "OrderTag"]


def test_two_readless_predicate_writes_partition_the_buffer_into_three_regions() -> None:
    buffer: list[BufferItem] = [
        KeyedWrite("delete", "Order", ({"id": 1},)),
        _predicate_update("Order"),
        KeyedWrite("delete", "OrderItem", ({"id": 10},)),
        KeyedWrite(
            "insert",
            "Order",
            ({"id": 2, "name": "N", "qty": 1, "price": 1.0, "active": True, "orderedOn": _B1},),
        ),
        _predicate_update("OrderItem"),
        KeyedWrite("insert", "OrderItem", ({"id": 11, "orderId": 2, "sku": "A", "quantity": 1},)),
    ]
    plan = _plan(buffer, _ORDERS)
    assert _shape(plan) == [
        ("delete", "Order"),
        ("update", "Order"),
        ("insert", "Order"),
        ("delete", "OrderItem"),
        ("update", "OrderItem"),
        ("insert", "OrderItem"),
    ]


# --------------------------------------------------------------------------- #
# Elision (m-unit-work "eliminate known cancellation and no-op work").        #
# --------------------------------------------------------------------------- #
def test_empty_change_set_update_emits_no_instruction() -> None:
    update = KeyedWrite("update", "Wallet", ({"id": 1},))  # only the PK: no changed field
    plan = _plan([update], _WALLET)
    assert len(plan.steps) == 0


def test_nonempty_change_set_update_survives_elision() -> None:
    update = KeyedWrite("update", "Wallet", ({"id": 1, "balance": 7.00},))
    plan = _plan([update], _WALLET)
    assert len(plan.steps) == 1


def test_empty_plan_from_empty_buffer() -> None:
    plan = _plan([], _ACCOUNT)
    assert plan == WritePlan()
    assert len(plan.steps) == 0


# --------------------------------------------------------------------------- #
# Object identity (unaffected by the planner surface — a standalone helper).  #
# --------------------------------------------------------------------------- #
def test_object_key_of_a_single_row_keyed_write() -> None:
    key_ = object_key(KeyedWrite("update", "Account", ({"id": 1, "balance": 0},)), _ACCOUNT)
    assert key_ == corpus_object_key("Account", ("id", 1))


def test_object_key_is_none_for_unidentifiable_writes() -> None:
    assert object_key(KeyedWrite("insert", "Account", ({"id": 1}, {"id": 2})), _ACCOUNT) is None
    assert object_key(KeyedWrite("insert", "Account", ({"owner": "Ada"},)), _ACCOUNT) is None
    predicate = PredicateWrite("delete", PredicateSelection("Account", op_algebra.All()))
    assert object_key(predicate, _ACCOUNT) is None


def test_object_key_is_none_for_an_entity_the_model_does_not_declare() -> None:
    assert object_key(KeyedWrite("delete", "Blob", ({"data": "x"},)), _ACCOUNT) is None


def test_object_key_names_the_resolved_identity_not_the_instructions_spelling() -> None:
    # A write instruction is a serialized document, so it carries whichever
    # spelling its author wrote. Both name one Entity, so both must reach the
    # one key an observation was recorded under — the key names the RESOLVED
    # Entity Identity rather than the spelling that reached it.
    row = ({"id": 1, "balance": 0},)
    bare = object_key(KeyedWrite("update", "Account", row), _ACCOUNT)
    canonical = object_key(KeyedWrite("update", "parallax.compatibility.Account", row), _ACCOUNT)
    assert bare == canonical == corpus_object_key("Account", ("id", 1))


def test_object_key_resolves_the_family_effective_primary_key() -> None:
    # `CardPayment`'s own compiled record carries no `id` attribute at all (it
    # is declared on the family root `Payment` alone, m-inheritance "Inherited
    # members") -- a bare `Entity.primary_key` view would wrongly see no key,
    # making every inheritance-family keyed write unidentifiable.
    key_ = object_key(KeyedWrite("update", "CardPayment", ({"id": 1, "amount": 5.00},)), _PAYMENT)
    assert key_ == corpus_object_key("CardPayment", ("id", 1))


def test_object_key_is_none_for_a_marker_shaped_primary_key_value() -> None:
    # A pk-gen `max` insert's row carries a DB-computed marker for the id, not
    # a real value (`{computed: "maxPlusOne"}`, `m-pk-gen`): it has no
    # coalescing identity, exactly like an absent pk.
    marker_insert = KeyedWrite(
        "insert", "Attendee", ({"id": {"computed": "maxPlusOne"}, "name": "Ada"},)
    )
    assert object_key(marker_insert, _PK_MAX) is None
    # And it must not crash any planning stage that keys off it.
    plan = _plan([marker_insert], _PK_MAX)
    (step,) = plan.steps
    assert isinstance(step, PlannedInsert)
    (row,) = _insert_rows(step)
    assert row["id"] == MAX_PLUS_ONE


def test_recorded_observations_bind_to_their_own_planned_update() -> None:
    row1 = KeyedWrite("update", "Account", ({"id": 1, "balance": 0.00},))
    row2 = KeyedWrite("update", "Account", ({"id": 2, "balance": 0.00},))
    key1 = object_key(row1, _ACCOUNT)
    key2 = object_key(row2, _ACCOUNT)
    assert key1 is not None and key2 is not None
    plan = _plan(
        [row1, row2],
        _ACCOUNT,
        observations={
            key1: VersionObservation(observed_version=3),
            key2: VersionObservation(observed_version=10),
        },
    )
    advanced = {}
    for step in plan.steps:
        assert isinstance(step, PlannedUpdate)
        row_id = _single_key(step)
        advanced[row_id] = _row_values_from_assignments(step)["version"]
    assert advanced == {1: 4, 2: 11}  # each advances from its OWN recorded observation


def _row_values_from_assignments(step: PlannedUpdate) -> dict[str, object]:
    values: dict[str, object] = {
        ident.name: value for ident, value in step.assignments.attributes.items()
    }
    for ident, value in step.assignments.value_objects.items():
        values[ident.path[-1]] = value
    return values


# --------------------------------------------------------------------------- #
# Affected-rows policy and optimistic gates (m-opt-lock, ADR 0044/0047).      #
# --------------------------------------------------------------------------- #
def test_a_versioned_update_with_a_recorded_observation_carries_a_settled_gate() -> None:
    update = KeyedWrite("update", "Account", ({"id": 1, "balance": 175.00},))
    key_ = object_key(update, _ACCOUNT)
    assert key_ is not None
    plan = _plan(
        [update],
        _ACCOUNT,
        observations={key_: VersionObservation(observed_version=3)},
        concurrency="optimistic",
    )
    (step,) = plan.steps
    assert isinstance(step, PlannedUpdate)
    version = next(ident for ident in step.assignments.attributes if ident.name == "version")
    assert step.concurrency == Versioned(gate=VersionGate(attribute=version, observed_version=3))
    assert step.affected_rows == ExactCount(1, OPTIMISTIC_CONFLICT)


def test_a_versioned_delete_with_a_recorded_observation_is_ungated_under_locking() -> None:
    delete = KeyedWrite("delete", "Account", ({"id": 1},))
    key_ = object_key(delete, _ACCOUNT)
    assert key_ is not None
    plan = _plan([delete], _ACCOUNT, observations={key_: VersionObservation(observed_version=3)})
    (step,) = plan.steps
    assert isinstance(step, PlannedDelete)
    assert step.concurrency == Versioned(gate=UNGATED)
    assert step.affected_rows == ExactCount(1, STALE_WRITE)


def test_an_observation_free_multi_key_delete_carries_the_aggregate_missing_target_policy() -> None:
    delete = KeyedWrite("delete", "Wallet", ({"id": 1}, {"id": 2}))
    plan = _plan([delete], _WALLET)
    (step,) = plan.steps
    assert isinstance(step, PlannedDelete)
    assert isinstance(step.target, KeyTarget)
    assert step.target.key_values == ((1,), (2,))
    # One multi-key Key Target owns ONE aggregate expectation (ADR 0044): the
    # target's own key count, classified by the observation-free keyed rule.
    assert step.affected_rows == ExactCount(2, MISSING_TARGET)


def test_a_readless_predicate_write_carries_an_unbounded_expectation() -> None:
    predicate = PredicateWrite(
        "delete",
        PredicateSelection("Wallet", op_algebra.Comparison("lessThan", "Wallet.balance", 200.00)),
    )
    plan = _plan([predicate], _WALLET)
    (step,) = plan.steps
    assert isinstance(step, PlannedDelete)
    assert step.affected_rows == ANY_COUNT


# --------------------------------------------------------------------------- #
# Batching (m-batch-write's collapse-eligibility policy, production-wired).   #
# --------------------------------------------------------------------------- #
def test_batching_merges_adjacent_same_entity_same_mutation_inserts() -> None:
    buffer: list[BufferItem] = [
        KeyedWrite("insert", "Wallet", ({"id": 1, "owner": "Ada", "balance": 1.00},)),
        KeyedWrite("insert", "Wallet", ({"id": 2, "owner": "Bo", "balance": 2.00},)),
        KeyedWrite("insert", "Wallet", ({"id": 3, "owner": "Cy", "balance": 3.00},)),
    ]
    plan = _plan(buffer, _WALLET)
    (step,) = plan.steps
    assert isinstance(step, PlannedInsert)
    assert len(step.entries) == 3


def test_batching_merges_uniform_updates_but_not_a_lone_row() -> None:
    buffer: list[BufferItem] = [KeyedWrite("update", "Wallet", ({"id": 1, "balance": 5.00},))]
    plan = _plan(buffer, _WALLET)
    (step,) = plan.steps
    assert isinstance(step, PlannedUpdate)
    assert len(_key_values(step)) == 1  # a single row is never a "run"


def test_a_known_no_op_between_two_uniform_updates_does_not_prevent_their_batch() -> None:
    # No-op elimination (m-unit-work stage 2) precedes batching (stage 4): a
    # buffered update naming only its own primary key is eliminated before
    # `_form_batches` ever sees the buffer, so it cannot occupy the run
    # boundary between the two uniform updates surrounding it. Batching first
    # would instead leave the no-op splitting the run, and the two survivors
    # would settle as two separate singleton steps rather than one batch.
    buffer: list[BufferItem] = [
        KeyedWrite("update", "Wallet", ({"id": 1, "balance": 5.00},)),
        KeyedWrite("update", "Wallet", ({"id": 2},)),  # a known no-op: only the PK
        KeyedWrite("update", "Wallet", ({"id": 3, "balance": 5.00},)),
    ]
    plan = _plan(buffer, _WALLET)
    (step,) = plan.steps
    assert isinstance(step, PlannedUpdate)
    assert _key_values(step) == ((1,), (3,))


def test_batching_declines_a_non_uniform_update_run_leaving_rows_separate() -> None:
    buffer: list[BufferItem] = [
        KeyedWrite("update", "Wallet", ({"id": 1, "balance": 111.00},)),
        KeyedWrite("update", "Wallet", ({"id": 2, "balance": 222.00},)),
    ]
    plan = _plan(buffer, _WALLET)
    assert len(plan.steps) == 2  # `batch_write.update_collapses` declines: not uniform


def test_batching_never_regroups_across_an_intervening_different_entity() -> None:
    buffer: list[BufferItem] = [
        KeyedWrite("insert", "Wallet", ({"id": 1, "owner": "Ada", "balance": 1.00},)),
        KeyedWrite("insert", "Person", ({"id": 99, "name": "P"},)),
        KeyedWrite("insert", "Wallet", ({"id": 2, "owner": "Bo", "balance": 2.00},)),
    ]
    model = models.accepted_model(
        DescriptorMetamodel(entities=(*_MODELS["wallet"].entities, *_MODELS["person"].entities))
    )
    plan = _plan(buffer, model)
    # Dependency ordering groups all inserts together, but the two Wallet rows
    # were NEVER adjacent in BUFFER order (Person interrupted the run), so they
    # stay two separate single-row instructions rather than merging into one.
    wallet_steps = [
        step
        for step in plan.steps
        if isinstance(step, PlannedInsert) and step.entity.name == "Wallet"
    ]
    assert len(wallet_steps) == 2


def test_batching_never_merges_a_row_carrying_a_recorded_observation() -> None:
    # A row explicitly signalled as separately-observed (e.g. an engine
    # `observedVersion` control key, or a real transaction-scoped
    # `uow.observe`) is never a merge candidate: a multi-row instruction has
    # no way to carry a per-row observation forward.
    row1 = KeyedWrite("update", "Wallet", ({"id": 1, "balance": 5.00},))
    row2 = KeyedWrite("update", "Wallet", ({"id": 2, "balance": 5.00},))
    key1 = object_key(row1, _WALLET)
    assert key1 is not None
    # Wallet is unversioned, so this key carries no meaningful observation
    # value — its mere presence in the map is what forces separation.
    plan = _plan([row1, row2], _WALLET, observations={key1: VersionObservation(observed_version=1)})
    assert len(plan.steps) == 2


def test_batching_never_merges_across_an_intervening_materialized_write_group() -> None:
    # A Materialized Write Group is opaque to batching AND a hard run
    # boundary: the two surrounding uniform updates are individually
    # batch-eligible, but merging them would emit the caller's second update
    # BEFORE the group the caller buffered between them.
    group = _version_group(
        "Wallet", "update", "id", [(9, 1)], [WriteAssignment("Wallet.balance", 5.00)]
    )
    buffer: list[BufferItem] = [
        KeyedWrite("update", "Wallet", ({"id": 1, "balance": 5.00},)),
        group,
        KeyedWrite("update", "Wallet", ({"id": 2, "balance": 5.00},)),
    ]
    plan = _plan(buffer, _WALLET)
    ids: list[object] = []
    for step in plan.steps:
        assert isinstance(step, PlannedUpdate)
        ids.extend(v for (v,) in _key_values(step))
    assert ids == [1, 9, 2]


def test_batching_never_touches_a_predicate_write() -> None:
    predicate = PredicateWrite(
        "delete",
        PredicateSelection("Wallet", op_algebra.Comparison("lessThan", "Wallet.balance", 1.0)),
    )
    plan = _plan([predicate], _WALLET)
    (step,) = plan.steps
    assert isinstance(step, PlannedDelete)
    assert step.target == PredicateTarget(
        predicate=op_algebra.Comparison("lessThan", "Wallet.balance", 1.0)
    )


# --------------------------------------------------------------------------- #
# Materialized Write Group (`m-unit-work` "Materialized Write Groups", ADR    #
# 0014): exempt from coalescing and from batching; dependency ordering moves  #
# it as ONE block; settles lazily into one `PlannedWrite` per resolved row.   #
# --------------------------------------------------------------------------- #
def test_materialized_group_settles_to_one_step_per_resolved_row_in_order() -> None:
    group = _version_group(
        "Account", "update", "id", [(1, 1), (2, 1)], [WriteAssignment("Account.balance", 10.00)]
    )
    plan = _plan([group], _ACCOUNT)
    assert len(plan.steps) == 2
    ids: list[object] = []
    for step in plan.steps:
        assert isinstance(step, PlannedUpdate)
        ids.append(_single_key(step))
    assert ids == [1, 2]


def test_materialized_group_rejects_an_authored_version_assignment() -> None:
    # A materializing predicate update's own assignment can never author the
    # version attribute — the version is framework-owned end to end (`m-opt-
    # lock` "Version values are framework-owned") — checked once for the
    # whole group, since every resolved row shares the same assignment.
    group = _version_group(
        "Account", "update", "id", [(1, 1)], [WriteAssignment("Account.version", 9)]
    )
    with pytest.raises(opt_lock.CallerAuthoredVersionError, match="framework-owned"):
        _plan([group], _ACCOUNT)


def test_materialized_group_is_exempt_from_same_object_coalescing() -> None:
    # A group's own row is never folded with an unrelated buffered insert of
    # the SAME object identity — it passes through coalesce opaque.
    insert = KeyedWrite("insert", "Account", ({"id": 1, "owner": "Ada", "balance": 1.00},))
    group = _version_group(
        "Account", "update", "id", [(1, 1)], [WriteAssignment("Account.balance", 2.00)]
    )
    plan = _plan([insert, group], _ACCOUNT)
    assert _shape(plan) == [("insert", "Account"), ("update", "Account")]


def test_materialized_group_is_exempt_from_batching() -> None:
    # A group's OWN member rows never re-batch into a multi-row instruction,
    # even when they would otherwise be eligible (adjacent, same entity/
    # mutation, uniform values) — each per-row gated write stays its own step
    # (`m-batch-write`).
    group = _version_group(
        "Wallet", "update", "id", [(1, 1), (2, 1)], [WriteAssignment("Wallet.balance", 5.00)]
    )
    plan = _plan([group], _WALLET)
    assert len(plan.steps) == 2


def test_materialized_group_moves_as_one_block_under_dependency_ordering() -> None:
    # The group's own rows (Order, an FK-referenced parent) stay ADJACENT and
    # in their OWN resolved-row order, moved as a whole relative to the OTHER
    # buffered instruction (an OrderItem insert, a child) — ordering alone
    # would otherwise put child-then-parent writes in a DIFFERENT relative
    # position than the group's own internal order. Order is unversioned, so
    # a plain delete carries no assignment to keep uniform across rows.
    group = _version_group("Order", "delete", "id", [(2, 1), (1, 1)])
    other = KeyedWrite(
        "insert", "OrderItem", ({"id": 10, "orderId": 1, "sku": "A", "quantity": 1},)
    )
    plan = _plan([group, other], _ORDERS)
    shapes: list[tuple[str, str, object]] = []
    for step in plan.steps:
        if isinstance(step, PlannedInsert):
            shapes.append(("insert", "OrderItem", _insert_rows(step)[0]["id"]))
        else:
            assert isinstance(step, PlannedDelete)
            shapes.append(("delete", "Order", _single_key(step)))
    # inserts before updates/deletes — the canonical INSERT -> UPDATE -> DELETE
    # order; the group's OWN two rows stay adjacent and in their OWN resolved
    # order (2 then 1), never re-sorted by id.
    assert shapes == [("insert", "OrderItem", 10), ("delete", "Order", 2), ("delete", "Order", 1)]


# --------------------------------------------------------------------------- #
# Transaction Instant laziness through the full pipeline (ADR 0010).          #
# --------------------------------------------------------------------------- #
def test_planning_never_captures_the_transaction_instant_for_canceled_work() -> None:
    # The stage order's whole point: coalescing cancels the pair before any
    # surviving write could need a Transaction-Time boundary, so the clock
    # behind the holder the request carries is never consulted.
    clock = CountingClock([dt.datetime(2024, 6, 1, tzinfo=dt.UTC)])
    insert = KeyedWrite("insert", "Account", ({"id": 1, "owner": "Ada", "balance": 1.00},))
    delete = KeyedWrite("delete", "Account", ({"id": 1},))
    plan = _plan([insert, delete], _ACCOUNT, tx_instant=TransactionInstant(clock))
    assert len(plan.steps) == 0
    assert clock.calls == 0


def test_planning_captures_the_transaction_instant_only_for_surviving_temporal_work() -> None:
    clock = CountingClock([dt.datetime(2024, 6, 1, tzinfo=dt.UTC)])
    non_temporal = KeyedWrite("insert", "Wallet", ({"id": 1, "owner": "Ada", "balance": 1.00},))
    plan = _plan([non_temporal], _WALLET, tx_instant=TransactionInstant(clock))
    assert len(plan.steps) == 1
    assert clock.calls == 0

    temporal_clock = CountingClock([dt.datetime(2024, 6, 1, tzinfo=dt.UTC)])
    temporal = KeyedWrite("insert", "Balance", ({"id": 1, "acctNum": "A", "value": 1.00},))
    plan = _plan([temporal], _BALANCE, tx_instant=TransactionInstant(temporal_clock))
    (step,) = plan.steps
    assert isinstance(step, PlannedInsert)
    assert _insert_rows(step)[0]["txStart"] == "2024-06-01T00:00:00+00:00"
    assert temporal_clock.calls == 1


# --------------------------------------------------------------------------- #
# Temporal in-place adjacency (ADR 0045): a close and its successors stay      #
# adjacent at the mutation's already-decided position, no unrelated step      #
# interleaved, through the SAME ordering + settling pipeline as everything    #
# else.                                                                        #
# --------------------------------------------------------------------------- #
def test_a_bounded_bitemporal_update_expands_in_place_between_unrelated_writes() -> None:
    # Dependency ordering buckets by verb (inserts, then updates, then
    # deletes) within one region, so an unrelated INSERT and an unrelated
    # DELETE naturally flank the temporal UPDATE bucket — exactly the position
    # its close-and-successors run must occupy as one indivisible unit.
    position_update = KeyedWrite(
        "update", "Position", ({"id": 5, "value": 42.0},), valid_from="2024-03-01T00:00:00+00:00"
    )
    key_ = object_key(position_update, _POSITION)
    assert key_ is not None
    buffer: list[BufferItem] = [
        KeyedWrite("insert", "Wallet", ({"id": 1, "owner": "Ada", "balance": 1.00},)),
        position_update,
        KeyedWrite("delete", "Wallet", ({"id": 2},)),
    ]
    model = models.accepted_model(
        DescriptorMetamodel(entities=(*_MODELS["wallet"].entities, *_MODELS["position"].entities))
    )
    plan = _plan(
        buffer,
        model,
        observations={key_: _bitemporal_observation()},
        tx_instant=instant_at("2024-06-01T00:00:00+00:00"),
    )
    kinds = [_step_mutation(step) for step in plan.steps]
    assert kinds[0] == "insert"
    assert kinds[-1] == "delete"
    middle = kinds[1:-1]
    assert middle[0] == "close"
    assert all(k == "insert" for k in middle[1:])
    assert len(middle) >= 2  # a close plus at least one chained successor


def _bitemporal_observation() -> WriteObservation:
    return TemporalObservation(
        predecessor=PredecessorRow(
            members={
                "id": 5,
                "acctNum": "P5",
                "value": 1.0,
                "validStart": "2024-01-01T00:00:00+00:00",
                "validEnd": "infinity",
                "txStart": "2024-01-01T00:00:00+00:00",
                "txEnd": "infinity",
            }
        ),
        transaction_time_basis=LATEST_PINNED,
    )
