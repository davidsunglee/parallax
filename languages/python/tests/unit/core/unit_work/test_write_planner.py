"""``WritePlanner.finalize`` — the primary neutral seam (m-unit-work, Docker-free).

``WritePlanner.finalize(PlanningRequest) -> WritePlanningResult`` is the entire
caller-visible planning surface: no caller sequences coalescing, batching,
ordering, temporal expansion, observation validation, instant acquisition, or
provenance decoration by hand. A caller does resolve the observation a write
settles against, at the verb that holds the value, and buffers it on the write.
These tests drive it directly — through the
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

import dataclasses
import datetime as dt
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, cast

import pytest

from parallax.core import bitemp_write, inheritance, relationship, temporal_read, txtime_write
from parallax.core import predicate as predicate_algebra
from parallax.core._formation_profile import form_metamodel
from parallax.core.base import INFINITY
from parallax.core.db_port import JsonDocument
from parallax.core.dialect import POSTGRES
from parallax.core.document_codec import PreparedEffectiveChange, prepare_effective_change
from parallax.core.entity._construction_input import ABSENT
from parallax.core.entity._layout import LayoutCatalog
from parallax.core.entity._model import model_of
from parallax.core.metamodel import (
    AttributeIdentity,
    AttributeMetadata,
    AttributeReference,
    Cardinality,
    EntityIdentity,
    Metamodel,
    RelationshipIdentity,
    RelativeEntityReference,
    Table,
    TemporalDimension,
    UnresolvedDefiningRelationshipDeclaration,
    UnresolvedRelationshipJoin,
)
from parallax.core.opt_lock import CallerAuthoredVersionError
from parallax.core.relationship import _compile as relationship_compile
from parallax.core.sql_gen._write import compile_write_step
from parallax.core.unit_work import (
    BufferItem,
    Concurrency,
    KeyedWrite,
    MaterializedWriteGroup,
    MilestoneTopology,
    ObjectKey,
    PlannedClose,
    PlannedInsert,
    PlanningRequest,
    PredecessorRow,
    PredecessorRows,
    PredecessorRowsBuilder,
    PredicateMutation,
    PredicateSelection,
    PredicateWrite,
    RetainedObservation,
    TemporalObservation,
    TransactionInstant,
    VersionedEvidenceBuilder,
    VersionObservation,
    WriteAssignment,
    WriteObservation,
    WritePlan,
    WritePlanningError,
    object_key,
)
from parallax.core.unit_work import planner as planner_module
from parallax.core.unit_work import write_settlement as write_settlement_module
from parallax.core.unit_work.instructions import (
    PreparedAssignment,
    PreparedKeyedWrite,
    PreparedPredicateWrite,
    WriteInstructionError,
    prepare_typed_write,
)
from parallax.core.unit_work.materialized import ObjectClaimedWrite, ObservedKeyedWrite
from parallax.core.unit_work.planned import (
    ANY_COUNT,
    MAX_PLUS_ONE,
    MISSING_TARGET,
    OPTIMISTIC_CONFLICT,
    STALE_WRITE,
    UNGATED,
    UNVERSIONED,
    ChangedFrom,
    ExactCount,
    KeyTarget,
    PlannedDelete,
    PlannedRow,
    PlannedUpdate,
    PlannedWrite,
    TemporalGate,
    ValidatedMutationSelection,
    Versioned,
    VersionGate,
)
from parallax.core.unit_work.planner import VersionedStateKey
from parallax.core.unit_work.strategy import ActorIdentity
from parallax.descriptor._records import Metamodel as DescriptorMetamodel
from parallax.snapshot.handle import _planning as planning_composition
from parallax.snapshot.handle import build_write_planner
from tests._support.clock_probes import CountingClock, inert_instant, instant_at
from tests._support.planner_probes import TEST_ACTOR_IDENTITY, observed_buffer
from tests.unit import _predicate_acquisition_support as acquisition_support
from tests.unit._corpus_identity_support import corpus_entity, corpus_object_key
from tests.unit._corpus_model_support import corpus_records, formed
from tests.unit._corpus_model_support import model as corpus_model
from tests.unit._metamodel_support import Declaration, attribute, identity, key, source
from tests.unit._positional_row_support import positional_row
from tests.unit._temporal_group_support import temporal_group

_MODELS = corpus_records()
_ACCOUNT = corpus_model("account")
_BALANCE = corpus_model("balance")
_POSITION = corpus_model("position")
_ORDERS = corpus_model("orders")
_PERSON = corpus_model("person")
_PAYMENT = corpus_model("payment")
_PK_MAX = corpus_model("pk-max")
_WALLET = corpus_model("wallet")

_B1 = "2024-01-01T00:00:00.000000Z"
_B1_MANAGED = dt.datetime(2024, 1, 1, tzinfo=dt.UTC)

# The planner threads its Transaction Instant through untouched to whichever
# stage first needs it, so every non-temporal test below shares one uncaptured
# holder rather than pinning an instant it would never read.
_INSTANT = inert_instant()


type _TestBufferItem = BufferItem | KeyedWrite | PredicateWrite


def _plan(
    buffer: Sequence[_TestBufferItem],
    model: Metamodel,
    *,
    observations: dict[ObjectKey, WriteObservation] | None = None,
    concurrency: Concurrency = "locking",
    tx_instant: TransactionInstant | None = None,
) -> WritePlan:
    return (
        build_write_planner(model)
        .finalize(
            PlanningRequest(
                actor_identity=TEST_ACTOR_IDENTITY,
                transaction_instant=tx_instant if tx_instant is not None else _INSTANT,
                concurrency=concurrency,
                buffered_writes=observed_buffer(buffer, model, observations),
            )
        )
        .plan
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


def _prepared_keyed(write: KeyedWrite, model: Metamodel) -> PreparedKeyedWrite:
    prepared = prepare_typed_write(write, model)
    assert isinstance(prepared, PreparedKeyedWrite)
    return prepared


def _observed(
    write: KeyedWrite,
    observation: WriteObservation,
    *,
    claim: RetainedObservation | None = None,
    restorations: frozenset[str] = frozenset(),
) -> ObservedKeyedWrite:
    prepared = _prepared_keyed(write, _ACCOUNT)
    return ObservedKeyedWrite(prepared, observation, claim=claim, restorations=restorations)


def _claimed(
    write: KeyedWrite, *, restorations: frozenset[str] = frozenset()
) -> ObjectClaimedWrite:
    return ObjectClaimedWrite(_prepared_keyed(write, _WALLET), restorations=restorations)


def _version_group(
    entity: str,
    mutation: PredicateMutation,
    key_name: str,
    rows: Sequence[tuple[object, int]],
    assignments: Sequence[WriteAssignment] = (),
    model: Metamodel | None = None,
) -> MaterializedWriteGroup:
    """A minimal Materialized Write Group for planner-seam tests.

    ``rows`` is ``(key value, observed version)`` per resolved row; every row
    shares ``assignments`` uniformly, the real shape a materializing predicate
    write settles to (`m-unit-work` "Materialized Write Groups") — a
    Materialized Write Group carries no per-row assigned value, only per-row
    key and observation columns.
    """
    del key_name
    evidence = VersionedEvidenceBuilder(key_position=0, version_position=1)
    for key_value, version in rows:
        evidence.append((key_value, version))
    sealed = evidence.seal()
    assert sealed is not None
    predicate = PredicateWrite(
        mutation,
        PredicateSelection(
            entity, predicate_algebra.Comparison("lessThan", f"{entity}.balance", "1000000.00")
        ),
        assignments=tuple(
            WriteAssignment(
                assignment.attr,
                Decimal(str(assignment.value))
                if assignment.attr.endswith(".balance") and isinstance(assignment.value, float)
                else assignment.value,
            )
            for assignment in assignments
        ),
    )
    prepared = prepare_typed_write(
        predicate, model if model is not None else (_WALLET if entity == "Wallet" else _ACCOUNT)
    )
    assert isinstance(prepared, PreparedPredicateWrite)
    return MaterializedWriteGroup(mutation=prepared, evidence=sealed)


def _shape(plan: WritePlan) -> list[tuple[str, str]]:
    return [(_step_mutation(step), _step_entity(step)) for step in plan.steps]


# --------------------------------------------------------------------------- #
# Coalesce (m-unit-work "Same-transaction write coalescing").                 #
# --------------------------------------------------------------------------- #
def test_nontemporal_insert_then_update_coalesces_to_one_insert() -> None:
    insert = KeyedWrite(
        "insert", "Account", ({"id": 9, "owner": "Noether", "balance": Decimal("5.00")},)
    )
    update = KeyedWrite("update", "Account", ({"id": 9, "balance": Decimal("99.00")},))
    plan = _plan([insert, update], _ACCOUNT)
    (step,) = plan.steps
    assert isinstance(step, PlannedInsert)
    (row,) = _insert_rows(step)
    # A single INSERT with final values, never INSERT + UPDATE; the framework
    # still derives the initial version onto the ONE surviving row.
    assert row["owner"] == "Noether"
    assert row["balance"] == Decimal("99.00")
    assert row["version"] == 1


def test_two_assignments_of_one_observed_state_merge_with_the_later_value_winning() -> None:
    # Observed-State Coalescing: two writes settling against ONE observed state
    # over one region are one write. The assignments merge in authored order, so
    # a member only the first names survives and a member both name takes the
    # LAST authored value — never the first, which is what an accumulate-and-keep
    # merge would leave.
    key = corpus_object_key("Account", ("id", 1))
    observation = VersionObservation(observed_version=4)
    first = KeyedWrite(
        "update", "Account", ({"id": 1, "owner": "Grace", "balance": Decimal("125.00")},)
    )
    second = KeyedWrite("update", "Account", ({"id": 1, "balance": Decimal("175.00")},))
    plan = _plan([first, second], _ACCOUNT, observations={key: observation})
    (step,) = plan.steps
    assert isinstance(step, PlannedUpdate)
    assert _assignment_values(step) == {
        "owner": "Grace",
        "balance": Decimal("175.00"),
        "version": 5,
    }


def test_a_restored_member_is_dropped_after_the_merge_rather_than_before_it() -> None:
    # Effective-change elimination runs AFTER the merge, so the caller's last word
    # on a member decides whether it is written: the second write restores
    # `balance`, which erases the first write's assignment to it while leaving the
    # member only the first named standing.
    key = corpus_object_key("Account", ("id", 1))
    observation = VersionObservation(observed_version=4)
    first = KeyedWrite(
        "update", "Account", ({"id": 1, "owner": "Grace", "balance": Decimal("125.00")},)
    )
    second = KeyedWrite("update", "Account", ({"id": 1},))
    plan = _plan(
        [first, _observed(second, observation, restorations=frozenset({"balance"}))],
        _ACCOUNT,
        observations={key: observation},
    )
    (step,) = plan.steps
    assert isinstance(step, PlannedUpdate)
    assert _assignment_values(step) == {"owner": "Grace", "version": 5}


def test_a_wholly_restored_merge_leaves_no_step_at_all() -> None:
    # What is left names only the key, which is no work: stage 2 eliminates the
    # merged write exactly as it eliminates a lone key-only row, so a chain that
    # nets to zero across two verbs emits no DML.
    key = corpus_object_key("Account", ("id", 1))
    observation = VersionObservation(observed_version=4)
    first = KeyedWrite("update", "Account", ({"id": 1, "balance": Decimal("125.00")},))
    second = KeyedWrite("update", "Account", ({"id": 1},))
    plan = _plan(
        [first, _observed(second, observation, restorations=frozenset({"balance"}))],
        _ACCOUNT,
        observations={key: observation},
    )
    assert list(plan.steps) == []


def test_a_destructive_intent_supersedes_the_assignments_buffered_before_it() -> None:
    key = corpus_object_key("Account", ("id", 1))
    observation = VersionObservation(observed_version=4)
    update = KeyedWrite("update", "Account", ({"id": 1, "balance": Decimal("125.00")},))
    delete = KeyedWrite("delete", "Account", ({"id": 1},))
    plan = _plan([update, delete], _ACCOUNT, observations={key: observation})
    (step,) = plan.steps
    assert isinstance(step, PlannedDelete)


def test_identical_destructive_intents_of_one_state_plan_one_step() -> None:
    key = corpus_object_key("Account", ("id", 1))
    observation = VersionObservation(observed_version=4)
    delete = KeyedWrite("delete", "Account", ({"id": 1},))
    plan = _plan([delete, delete], _ACCOUNT, observations={key: observation})
    (step,) = plan.steps
    assert isinstance(step, PlannedDelete)


def test_writes_of_two_observed_states_of_one_object_stay_independent() -> None:
    # Coalescing is keyed by the observed STATE, not by the object: two writes
    # settling against two generations of one row are two intents, and merging
    # them would gate the survivor on a version one of them never saw.
    first = _observed(
        KeyedWrite("update", "Account", ({"id": 1, "balance": Decimal("125.00")},)),
        VersionObservation(observed_version=4),
    )
    second = _observed(
        KeyedWrite("update", "Account", ({"id": 1, "balance": Decimal("175.00")},)),
        VersionObservation(observed_version=5),
    )
    plan = _plan([first, second], _ACCOUNT, concurrency="optimistic")
    assert len(plan.steps) == 2


def test_a_second_state_of_one_object_does_not_close_the_first_states_claim() -> None:
    # An object's claims are open per observed STATE, so a write of one state
    # standing between two writes of another leaves their claim exactly where it
    # was: the verb admitted the third write as a merge into the first, and
    # emitting it separately would gate two statements on one generation — the
    # second of which no read ever saw current.
    earlier = VersionObservation(observed_version=4)
    later = VersionObservation(observed_version=5)
    first = _observed(
        KeyedWrite("update", "Account", ({"id": 1, "balance": Decimal("125.00")},)), earlier
    )
    interleaved = _observed(KeyedWrite("update", "Account", ({"id": 1, "owner": "Grace"},)), later)
    third = _observed(
        KeyedWrite("update", "Account", ({"id": 1, "balance": Decimal("175.00")},)), earlier
    )
    plan = _plan([first, interleaved, third], _ACCOUNT, concurrency="optimistic")
    merged, standing = plan.steps
    assert isinstance(merged, PlannedUpdate)
    assert isinstance(standing, PlannedUpdate)
    assert _assignment_values(merged) == {"balance": Decimal("175.00"), "version": 5}
    assert _assignment_values(standing) == {"owner": "Grace", "version": 6}


def test_object_claimed_writes_of_one_unversioned_row_merge_into_one_step() -> None:
    # The object-claimed arm reaches the same algebra by the same call: what such
    # writes share is the object, because no state stands behind them.
    first = _claimed(KeyedWrite("update", "Wallet", ({"id": 1, "balance": Decimal("5.00")},)))
    second = _claimed(KeyedWrite("update", "Wallet", ({"id": 1, "owner": "Grace"},)))
    plan = _plan([first, second], _WALLET)
    (step,) = plan.steps
    assert isinstance(step, PlannedUpdate)
    assert _assignment_values(step) == {"balance": Decimal("5.00"), "owner": "Grace"}


def test_an_object_claimed_destruction_supersedes_the_assignment_before_it() -> None:
    update = _claimed(KeyedWrite("update", "Wallet", ({"id": 1, "balance": Decimal("5.00")},)))
    delete = _claimed(KeyedWrite("delete", "Wallet", ({"id": 1},)))
    plan = _plan([update, delete], _WALLET)
    (step,) = plan.steps
    assert isinstance(step, PlannedDelete)


def test_identical_object_claimed_destructions_plan_one_step() -> None:
    # Unclaimed, the pair reaches the batch collapse as a repeated authored key,
    # which a Key Target refuses — so deduplication is what keeps a legal two-verb
    # sequence out of an internal invariant failure.
    delete = _claimed(KeyedWrite("delete", "Wallet", ({"id": 1},)))
    plan = _plan([delete, delete], _WALLET)
    (step,) = plan.steps
    assert isinstance(step, PlannedDelete)


def test_a_wholly_restoring_object_claimed_merge_leaves_no_step_at_all() -> None:
    first = _claimed(KeyedWrite("update", "Wallet", ({"id": 1, "balance": Decimal("5.00")},)))
    second = _claimed(
        KeyedWrite("update", "Wallet", ({"id": 1},)), restorations=frozenset({"balance"})
    )
    plan = _plan([first, second], _WALLET)
    assert list(plan.steps) == []


def test_object_claimed_writes_of_two_rows_still_collapse_into_one_batch() -> None:
    # A claim is per object, so two objects' deletes are two claims — and each
    # leaves coalescing as the bare instruction it always was, which is what keeps
    # `m-batch-write`'s set-based collapse reachable for unversioned rows.
    first = _claimed(KeyedWrite("delete", "Wallet", ({"id": 1},)))
    second = _claimed(KeyedWrite("delete", "Wallet", ({"id": 2},)))
    plan = _plan([first, second], _WALLET)
    (step,) = plan.steps
    assert isinstance(step, PlannedDelete)
    assert isinstance(step.target, KeyTarget)
    assert step.target.key_values == ((1,), (2,))


def _assignment_values(step: PlannedUpdate) -> dict[str, object]:
    return {ident.name: value for ident, value in step.assignments.attributes.items()}


def test_audit_insert_then_update_coalesces_in_place() -> None:
    insert = KeyedWrite(
        "insert", "Balance", ({"id": 9, "acctNum": "D", "value": Decimal("100.00")},)
    )
    update = KeyedWrite("update", "Balance", ({"id": 9, "value": Decimal("150.00")},))
    plan = _plan([insert, update], _BALANCE, tx_instant=instant_at(_B1))
    (step,) = plan.steps
    assert isinstance(step, PlannedInsert)  # one current milestone, no close
    (row,) = _insert_rows(step)
    assert row["acctNum"] == "D"
    assert row["value"] == Decimal("150.00")
    assert row["txStart"] == _B1_MANAGED


def test_bitemporal_insert_then_update_keeps_the_valid_time_bound() -> None:
    insert = KeyedWrite(
        "insert",
        "Position",
        ({"id": 9, "acctNum": "D", "value": Decimal("100.00")},),
        valid_from=_B1_MANAGED,
    )
    update = KeyedWrite("update", "Position", ({"id": 9, "value": Decimal("150.00")},))
    plan = _plan([insert, update], _POSITION, tx_instant=instant_at(_B1))
    (step,) = plan.steps
    assert isinstance(step, PlannedInsert)  # one fully-current rectangle, no head/tail split
    (row,) = _insert_rows(step)
    assert row["acctNum"] == "D"
    assert row["value"] == Decimal("150.00")
    assert row["validStart"] == _B1_MANAGED


def test_insert_then_delete_cancels_to_no_dml() -> None:
    insert = KeyedWrite(
        "insert", "Account", ({"id": 9, "owner": "Noether", "balance": Decimal("5.00")},)
    )
    delete = KeyedWrite("delete", "Account", ({"id": 9},))
    plan = _plan([insert, delete], _ACCOUNT)
    assert len(plan.steps) == 0  # both annihilate — the net-zero elision across two verbs


def test_insert_then_multiple_updates_fold_into_one_insert() -> None:
    insert = KeyedWrite(
        "insert", "Account", ({"id": 9, "owner": "Noether", "balance": Decimal("5.00")},)
    )
    update1 = KeyedWrite("update", "Account", ({"id": 9, "balance": Decimal("50.00")},))
    update2 = KeyedWrite("update", "Account", ({"id": 9, "owner": "Markov"},))
    plan = _plan([insert, update1, update2], _ACCOUNT)
    (step,) = plan.steps
    (row,) = _insert_rows(step)
    assert row["owner"] == "Markov"
    assert row["balance"] == Decimal("50.00")


def test_update_of_a_row_not_inserted_this_transaction_is_not_coalesced() -> None:
    update = KeyedWrite("update", "Wallet", ({"id": 1, "balance": Decimal("0.00")},))
    plan = _plan([update], _WALLET)
    (step,) = plan.steps
    assert isinstance(step, PlannedUpdate)


def test_delete_of_a_row_not_inserted_this_transaction_is_not_coalesced() -> None:
    delete = KeyedWrite("delete", "Wallet", ({"id": 1},))
    plan = _plan([delete], _WALLET)
    (step,) = plan.steps
    assert isinstance(step, PlannedDelete)


def test_multi_row_and_predicate_writes_do_not_coalesce() -> None:
    # Wallet is unversioned and non-temporal, so a readless predicate write is
    # legal there. Neither input is a single-object keyed write, so both pass
    # through as independent steps.
    multi = KeyedWrite(
        "insert",
        "Wallet",
        (
            {"id": 8, "owner": "A", "balance": Decimal("1.00")},
            {"id": 9, "owner": "B", "balance": Decimal("2.00")},
        ),
    )
    predicate = PredicateWrite(
        "delete", PredicateSelection("Wallet", predicate_algebra.Comparison("eq", "Wallet.id", 1))
    )
    plan = _plan([multi, predicate], _WALLET)
    assert len(plan.steps) == 2


# --------------------------------------------------------------------------- #
# Dependency ordering (foreign-key parents-before-children).                  #
# --------------------------------------------------------------------------- #
def test_inserts_order_parents_before_children() -> None:
    buffer: list[_TestBufferItem] = [
        KeyedWrite("insert", "OrderStatus", ({"id": 100, "orderId": 1, "code": "new"},)),
        KeyedWrite(
            "insert", "OrderTag", ({"id": 1000, "orderId": 1, "label": "x", "priority": 1},)
        ),
        KeyedWrite("insert", "OrderItem", ({"id": 10, "orderId": 1, "sku": "A", "quantity": 1},)),
        KeyedWrite(
            "insert",
            "Order",
            (
                {
                    "id": 1,
                    "name": "N",
                    "qty": 1,
                    "price": Decimal("1.0"),
                    "active": True,
                    "orderedOn": dt.date(2024, 1, 1),
                },
            ),
        ),
    ]
    plan = _plan(buffer, _ORDERS)
    assert _entities(plan) == ["Order", "OrderItem", "OrderStatus", "OrderTag"]


def test_deletes_order_children_before_parents() -> None:
    buffer: list[_TestBufferItem] = [
        KeyedWrite("delete", "Order", ({"id": 1},)),
        KeyedWrite("delete", "OrderItem", ({"id": 10},)),
        KeyedWrite("delete", "OrderStatus", ({"id": 100},)),
    ]
    plan = _plan(buffer, _ORDERS)
    assert _entities(plan) == ["OrderStatus", "OrderItem", "Order"]


def test_mixed_flush_is_insert_then_update_then_delete() -> None:
    buffer: list[_TestBufferItem] = [
        KeyedWrite("delete", "OrderStatus", ({"id": 100},)),
        KeyedWrite("update", "OrderItem", ({"id": 10, "quantity": 5},)),
        KeyedWrite(
            "insert",
            "Order",
            (
                {
                    "id": 2,
                    "name": "N",
                    "qty": 1,
                    "price": Decimal("1.0"),
                    "active": True,
                    "orderedOn": dt.date(2024, 1, 1),
                },
            ),
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
    buffer: list[_TestBufferItem] = [
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
    buffer: list[_TestBufferItem] = [
        KeyedWrite("insert", "Alpha", ({"id": 1, "zetaId": 2},)),
        KeyedWrite("insert", "Zeta", ({"id": 2},)),
    ]
    assert _entities(_plan(buffer, model)) == ["Zeta", "Alpha"]


def test_ordering_reads_each_ranked_writes_compiled_rank_once_and_derives_none(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Ranks are the Relationship Facet's, compiled with the model: a flush only
    # reads one per insert or delete. Updates keep authored order and the
    # barrier keeps its place, so neither asks.
    planner = build_write_planner(_ORDERS)
    facet = relationship.view(_ORDERS)
    asked: list[str] = []
    compiled = type(facet).referential_rank

    def recording(self: relationship.RelationshipFacet, entity: EntityIdentity) -> int | None:
        asked.append(entity.name)
        return compiled(self, entity)

    def refuse(*_: object) -> list[int]:
        raise AssertionError("a flush derived referential ranks")

    monkeypatch.setattr(type(facet), "referential_rank", recording)
    monkeypatch.setattr(relationship_compile, "_referential_ranks", refuse)
    buffer: list[_TestBufferItem] = [
        KeyedWrite("insert", "OrderItem", ({"id": 10, "orderId": 1, "sku": "A", "quantity": 1},)),
        KeyedWrite("update", "OrderItem", ({"id": 11, "quantity": 5},)),
        _predicate_update("Order"),
        KeyedWrite("delete", "OrderStatus", ({"id": 100},)),
        KeyedWrite("insert", "OrderTag", ({"id": 7, "orderId": 1, "label": "x", "priority": 1},)),
    ]
    request = PlanningRequest(
        actor_identity=TEST_ACTOR_IDENTITY,
        transaction_instant=_INSTANT,
        concurrency="locking",
        buffered_writes=observed_buffer(buffer, _ORDERS, None),
    )
    first = planner.finalize(request).plan
    second = planner.finalize(request).plan
    assert asked == ["OrderItem", "OrderStatus", "OrderTag"] * 2
    assert (
        _shape(first)
        == _shape(second)
        == [
            ("insert", "OrderItem"),
            ("update", "OrderItem"),
            ("update", "Order"),
            ("insert", "OrderTag"),
            ("delete", "OrderStatus"),
        ]
    )


def test_an_instruction_naming_an_undeclared_entity_is_a_planning_error() -> None:
    # Every settled step needs its Entity resolved (`_require_entity`), so an
    # instruction naming one the accepted Metamodel does not declare is refused
    # as a caller wiring defect during planning — never silently ranked first
    # by the ordering stage's own defensive fallback and lowered anyway.
    buffer: list[_TestBufferItem] = [
        KeyedWrite("insert", "OrderItem", ({"id": 10, "orderId": 1, "sku": "A", "quantity": 1},)),
        KeyedWrite("insert", "Gadget", ({"id": 1, "name": "G"},)),
    ]
    with pytest.raises(ValueError, match="Gadget"):
        _plan(buffer, _ORDERS)


def test_an_undeclared_entitys_keyed_update_survives_elision_to_the_same_refusal() -> None:
    # An undeclared entity is unresolvable for elision (its effective change set
    # cannot be proven empty), so a keyed update naming one is never silently
    # dropped as a no-op — it survives to the SAME planning refusal an insert of
    # an undeclared entity reaches. Isolated from the sibling test above (which
    # pairs an undeclared insert with a resolvable one): pairing this update with
    # any undeclared insert of the same entity would let the insert's own
    # refusal fire first and leave elision's behavior unobserved.
    buffer: list[_TestBufferItem] = [KeyedWrite("update", "Gadget", ({"id": 1},))]
    with pytest.raises(ValueError, match="Gadget"):
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
        PredicateSelection(entity, predicate_algebra.Comparison("eq", f"{entity}.id", 1)),
        assignments=(WriteAssignment(f"{entity}.{member}", "Z"),),
    )


def test_no_keyed_write_crosses_a_readless_predicate_write_in_either_direction() -> None:
    # The bucket sort alone would hoist the trailing insert to the front and
    # push the leading delete to the back, moving BOTH across the predicate
    # write — a readless predicate does not reveal which rows it matches, so
    # either move could change what it writes. The barrier pins all three.
    buffer: list[_TestBufferItem] = [
        KeyedWrite("delete", "OrderItem", ({"id": 10},)),
        _predicate_update("Order"),
        KeyedWrite(
            "insert",
            "Order",
            (
                {
                    "id": 2,
                    "name": "N",
                    "qty": 1,
                    "price": Decimal("1.0"),
                    "active": True,
                    "orderedOn": dt.date(2024, 1, 1),
                },
            ),
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
    assert isinstance(predicate_step.target, ValidatedMutationSelection)
    assert predicate_step.target.predicate.authored == predicate_algebra.Comparison(
        "eq", "Order.id", 1
    )


def test_fk_ordering_still_applies_independently_within_each_barrier_region() -> None:
    # Ordering is unconstrained WITHIN a region: each side is bucketed and
    # ordered on its own (parents before children), and the two sides never
    # see each other's items.
    buffer: list[_TestBufferItem] = [
        KeyedWrite("insert", "OrderItem", ({"id": 10, "orderId": 1, "sku": "A", "quantity": 1},)),
        KeyedWrite(
            "insert",
            "Order",
            (
                {
                    "id": 1,
                    "name": "N",
                    "qty": 1,
                    "price": Decimal("1.0"),
                    "active": True,
                    "orderedOn": dt.date(2024, 1, 1),
                },
            ),
        ),
        _predicate_update("OrderTag"),
        KeyedWrite(
            "insert", "OrderTag", ({"id": 1000, "orderId": 1, "label": "x", "priority": 1},)
        ),
        KeyedWrite("insert", "OrderStatus", ({"id": 100, "orderId": 1, "code": "new"},)),
    ]
    plan = _plan(buffer, _ORDERS)
    assert _entities(plan) == ["Order", "OrderItem", "OrderTag", "OrderStatus", "OrderTag"]


def test_two_readless_predicate_writes_partition_the_buffer_into_three_regions() -> None:
    buffer: list[_TestBufferItem] = [
        KeyedWrite("delete", "Order", ({"id": 1},)),
        _predicate_update("Order"),
        KeyedWrite("delete", "OrderItem", ({"id": 10},)),
        KeyedWrite(
            "insert",
            "Order",
            (
                {
                    "id": 2,
                    "name": "N",
                    "qty": 1,
                    "price": Decimal("1.0"),
                    "active": True,
                    "orderedOn": dt.date(2024, 1, 1),
                },
            ),
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
    update = KeyedWrite("update", "Wallet", ({"id": 1, "balance": Decimal("7.00")},))
    plan = _plan([update], _WALLET)
    assert len(plan.steps) == 1


def test_a_key_only_row_of_a_preformed_multi_row_update_is_eliminated() -> None:
    # Stage 2 eliminates known no-op work per ROW, not only per instruction: a
    # preformed update mixing a key-only row with an assigning one is not empty
    # as a whole, so an instruction-level test would pass it to batching, which
    # splits it into its rows and hands the key-only child an update with no
    # member to write. Eliminating the row here also keeps the elimination
    # ahead of batching, where the normative stage order puts it.
    update = KeyedWrite("update", "Wallet", ({"id": 1}, {"id": 2, "balance": Decimal("9.00")}))
    plan = _plan([update], _WALLET)
    (step,) = plan.steps
    assert isinstance(step, PlannedUpdate)
    assert _key_values(step) == ((2,),)


def test_a_preformed_update_whose_rows_are_all_key_only_is_eliminated_whole() -> None:
    update = KeyedWrite("update", "Wallet", ({"id": 1}, {"id": 2}))
    assert len(_plan([update], _WALLET).steps) == 0


def test_a_plural_temporal_update_is_refused_rather_than_narrowed_by_no_op_elimination() -> None:
    # Row-level elimination never rescues a plural temporal instruction into a
    # legal singleton: dropping the key-only row would silently discard one of
    # the two milestone chains the author wrote, which is exactly the reduction
    # `m-unit-work` requires an implementation to refuse.
    update = KeyedWrite("update", "Balance", ({"id": 1}, {"id": 2, "value": Decimal("9.00")}))
    with pytest.raises(ValueError, match="temporal target carries 2 rows"):
        _plan([update], _BALANCE)


def test_a_plural_temporal_update_of_key_only_rows_is_refused_rather_than_eliminated() -> None:
    # The same contract when elimination would take the WHOLE instruction: a
    # plural temporal update every row of which is key-only must still be
    # refused, because `m-unit-work`'s singleton rule admits no exception and an
    # empty plan would report that two authored milestone chains were fine. The
    # mixed-row shape above cannot pin this: there, a surviving row keeps the
    # instruction alive on its way to the refusal.
    update = KeyedWrite("update", "Balance", ({"id": 1}, {"id": 2}))
    with pytest.raises(ValueError, match="temporal target carries 2 rows"):
        _plan([update], _BALANCE)


def test_a_single_row_temporal_update_naming_only_its_key_is_still_eliminated() -> None:
    # Elimination is unchanged for the row count the singleton rule admits: one
    # temporal row assigning nothing opens no successor worth chaining, so
    # stage 2 removes it exactly as it removes a non-temporal one.
    update = KeyedWrite("update", "Balance", ({"id": 1},))
    assert len(_plan([update], _BALANCE).steps) == 0


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
    predicate = PredicateWrite("delete", PredicateSelection("Account", predicate_algebra.All()))
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
    key_ = object_key(
        KeyedWrite("update", "CardPayment", ({"id": 1, "amount": Decimal("5.00")},)), _PAYMENT
    )
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


def test_object_key_reads_the_family_key_its_owner_compiled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Formation proved the family has one key and the Inheritance Facet names
    # it at every position, so deriving an Object Key searches no declaration
    # for it — for a prepared write and a raw spelled one, at a standalone
    # Entity and at an inherited position alike. Preparation judges assignments
    # against the key Attribute, so it runs before discovery is refused.
    card = KeyedWrite("update", "CardPayment", ({"id": 1, "amount": Decimal("5.00")},))
    account = KeyedWrite("update", "Account", ({"id": 2, "balance": Decimal("0.00")},))
    prepared_card = _prepared_keyed(card, _PAYMENT)
    prepared_account = _prepared_keyed(account, _ACCOUNT)
    card_key = corpus_object_key("CardPayment", ("id", 1))
    account_key = corpus_object_key("Account", ("id", 2))

    def undiscoverable(attribute: AttributeMetadata) -> object:
        raise AssertionError(f"{attribute.identity} was searched for the family key")

    monkeypatch.setattr(AttributeMetadata, "primary_key", property(undiscoverable))
    assert object_key(prepared_card, _PAYMENT) == card_key
    assert object_key(card, _PAYMENT) == card_key
    assert object_key(prepared_account, _ACCOUNT) == account_key
    assert object_key(account, _ACCOUNT) == account_key


def test_recorded_observations_bind_to_their_own_planned_update() -> None:
    row1 = KeyedWrite("update", "Account", ({"id": 1, "balance": Decimal("0.00")},))
    row2 = KeyedWrite("update", "Account", ({"id": 2, "balance": Decimal("0.00")},))
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


def test_an_observation_on_an_unversioned_non_temporal_update_is_refused() -> None:
    # `m-unit-work`: "unversioned Non-Temporal writes have no observation", and
    # that absence is structural. The carrier can only refuse the half it can
    # see without the model (an insert, a plural instruction); the planner is
    # the model-aware boundary every carrier crosses, so it refuses the other
    # half rather than settling the write with the evidence discarded.
    update = KeyedWrite("update", "Wallet", ({"id": 1, "balance": Decimal("7.00")},))
    key_ = object_key(update, _WALLET)
    assert key_ is not None
    with pytest.raises(WritePlanningError, match="unversioned Non-Temporal 'update'"):
        _plan([update], _WALLET, observations={key_: VersionObservation(observed_version=3)})


def test_an_observation_on_an_unversioned_non_temporal_delete_is_refused() -> None:
    delete = KeyedWrite("delete", "Wallet", ({"id": 1},))
    key_ = object_key(delete, _WALLET)
    assert key_ is not None
    with pytest.raises(WritePlanningError, match="unversioned Non-Temporal 'delete'"):
        _plan([delete], _WALLET, observations={key_: VersionObservation(observed_version=3)})


def test_a_materialized_group_on_an_unversioned_non_temporal_target_is_refused() -> None:
    # The same rule one call deeper: a group's observation columns are not
    # optional either, so a group whose target turns out unversioned is refused
    # rather than settled Unversioned with every row's observed version dropped.
    group = _version_group(
        "Wallet",
        "update",
        "id",
        [(1, 7), (2, 8)],
        [WriteAssignment("Wallet.balance", Decimal("5.00"))],
    )
    with pytest.raises(WritePlanningError, match="unversioned Non-Temporal 'update'"):
        _plan([group], _WALLET, concurrency="optimistic")


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
    update = KeyedWrite("update", "Account", ({"id": 1, "balance": Decimal("175.00")},))
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
    assert step.concurrency == Versioned(attribute=version, gate=VersionGate(observed_version=3))
    assert step.affected_rows == ExactCount(1, OPTIMISTIC_CONFLICT)


def test_an_unversioned_target_settles_ungated_under_the_optimistic_preference() -> None:
    # The write half of the per-Entity derivation: `optimistic` is a preference,
    # not a strategy, so a family supplying no version source settles with no
    # gate — the same Unversioned decision the `locking` preference reaches
    # (`m-unit-work` "Strategy selection"). Its correctness comes from the
    # shared read lock its participating read took instead.
    delete = KeyedWrite("delete", "Wallet", ({"id": 1},))
    plan = _plan([delete], _WALLET, concurrency="optimistic")
    (step,) = plan.steps
    assert isinstance(step, PlannedDelete)
    assert step.concurrency == UNVERSIONED
    (under_locking,) = _plan([delete], _WALLET).steps
    assert isinstance(under_locking, PlannedDelete)
    assert under_locking.concurrency == step.concurrency


def test_a_versioned_delete_with_a_recorded_observation_is_ungated_under_locking() -> None:
    delete = KeyedWrite("delete", "Account", ({"id": 1},))
    key_ = object_key(delete, _ACCOUNT)
    assert key_ is not None
    plan = _plan([delete], _ACCOUNT, observations={key_: VersionObservation(observed_version=3)})
    (step,) = plan.steps
    assert isinstance(step, PlannedDelete)
    assert step.concurrency == Versioned(
        attribute=AttributeIdentity(_ACCOUNT.entities[0].identity, "version"), gate=UNGATED
    )
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


def test_an_unversioned_multi_key_update_settles_to_one_aggregate_planned_write() -> None:
    # The delete above proves the aggregate expectation on the destructive verb;
    # this is the assigning one, and together they fix the cardinality an
    # addressed write keeps whichever verb it carries. A collapsed run is ONE
    # statement over one multi-key Key Target, so it settles to one Planned
    # Update whose expectation is the whole target's key count — never one step
    # per key, which is the grain a Materialized Write Group settles at and an
    # addressed write never does.
    buffer: list[_TestBufferItem] = [
        KeyedWrite("update", "Wallet", ({"id": 1, "balance": Decimal("5.00")},)),
        KeyedWrite("update", "Wallet", ({"id": 2, "balance": Decimal("5.00")},)),
        KeyedWrite("update", "Wallet", ({"id": 3, "balance": Decimal("5.00")},)),
    ]
    plan = _plan(buffer, _WALLET)
    (step,) = plan.steps
    assert isinstance(step, PlannedUpdate)
    assert _key_values(step) == ((1,), (2,), (3,))
    assert step.concurrency == UNVERSIONED
    assert step.affected_rows == ExactCount(3, MISSING_TARGET)


def test_a_readless_predicate_write_carries_an_unbounded_expectation() -> None:
    predicate = PredicateWrite(
        "delete",
        PredicateSelection(
            "Wallet", predicate_algebra.Comparison("lessThan", "Wallet.balance", "200.00")
        ),
    )
    plan = _plan([predicate], _WALLET)
    (step,) = plan.steps
    assert isinstance(step, PlannedDelete)
    assert step.affected_rows == ANY_COUNT


# --------------------------------------------------------------------------- #
# Batching (m-batch-write's collapse-eligibility policy, production-wired).   #
# --------------------------------------------------------------------------- #
def test_batching_merges_adjacent_same_entity_same_mutation_inserts() -> None:
    buffer: list[_TestBufferItem] = [
        KeyedWrite("insert", "Wallet", ({"id": 1, "owner": "Ada", "balance": Decimal("1.00")},)),
        KeyedWrite("insert", "Wallet", ({"id": 2, "owner": "Bo", "balance": Decimal("2.00")},)),
        KeyedWrite("insert", "Wallet", ({"id": 3, "owner": "Cy", "balance": Decimal("3.00")},)),
    ]
    plan = _plan(buffer, _WALLET)
    (step,) = plan.steps
    assert isinstance(step, PlannedInsert)
    assert len(step.entries) == 3


def test_batching_merges_uniform_updates_but_not_a_lone_row() -> None:
    buffer: list[_TestBufferItem] = [
        KeyedWrite("update", "Wallet", ({"id": 1, "balance": Decimal("5.00")},))
    ]
    plan = _plan(buffer, _WALLET)
    (step,) = plan.steps
    assert isinstance(step, PlannedUpdate)
    assert len(_key_values(step)) == 1  # a single row is never a "run"


def test_a_known_no_op_between_two_uniform_updates_does_not_prevent_their_batch() -> None:
    # No-op elimination (m-unit-work stage 2) precedes batching (stage 3): a
    # buffered update naming only its own primary key is eliminated before
    # `_form_batches` ever sees the buffer, so it cannot occupy the run
    # boundary between the two uniform updates surrounding it. Batching first
    # would instead leave the no-op splitting the run, and the two survivors
    # would settle as two separate singleton steps rather than one batch.
    buffer: list[_TestBufferItem] = [
        KeyedWrite("update", "Wallet", ({"id": 1, "balance": Decimal("5.00")},)),
        KeyedWrite("update", "Wallet", ({"id": 2},)),  # a known no-op: only the PK
        KeyedWrite("update", "Wallet", ({"id": 3, "balance": Decimal("5.00")},)),
    ]
    plan = _plan(buffer, _WALLET)
    (step,) = plan.steps
    assert isinstance(step, PlannedUpdate)
    assert _key_values(step) == ((1,), (3,))


def test_batching_declines_a_non_uniform_update_run_leaving_rows_separate() -> None:
    buffer: list[_TestBufferItem] = [
        KeyedWrite("update", "Wallet", ({"id": 1, "balance": Decimal("111.00")},)),
        KeyedWrite("update", "Wallet", ({"id": 2, "balance": Decimal("222.00")},)),
    ]
    plan = _plan(buffer, _WALLET)
    assert len(plan.steps) == 2  # `batch_write.update_collapses` declines: not uniform


def test_batching_never_regroups_across_an_intervening_different_entity() -> None:
    buffer: list[_TestBufferItem] = [
        KeyedWrite("insert", "Wallet", ({"id": 1, "owner": "Ada", "balance": Decimal("1.00")},)),
        KeyedWrite("insert", "Person", ({"id": 99, "name": "P"},)),
        KeyedWrite("insert", "Wallet", ({"id": 2, "owner": "Bo", "balance": Decimal("2.00")},)),
    ]
    model = formed(
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
    # Two adjacent updates of one versioned entity assigning the SAME value are
    # exactly what the collapse decision admits — and they still settle as two
    # steps, because each arrives wrapped in its own observation carrier and a
    # multi-row instruction has no way to carry a per-row observation forward.
    # Both rows are observed because only an observed write of a versioned row
    # can be planned at all; the exclusion is therefore proven on the shape
    # production actually produces, not on an unversioned stand-in.
    row1 = KeyedWrite("update", "Account", ({"id": 1, "balance": Decimal("5.00")},))
    row2 = KeyedWrite("update", "Account", ({"id": 2, "balance": Decimal("5.00")},))
    key1, key2 = object_key(row1, _ACCOUNT), object_key(row2, _ACCOUNT)
    assert key1 is not None
    assert key2 is not None
    plan = _plan(
        [row1, row2],
        _ACCOUNT,
        observations={
            key1: VersionObservation(observed_version=1),
            key2: VersionObservation(observed_version=1),
        },
    )
    assert len(plan.steps) == 2


def test_batching_never_merges_across_an_intervening_materialized_write_group() -> None:
    # A Materialized Write Group is opaque to batching AND a hard run boundary.
    # The candidates around it are INSERTS, the one merge-eligible shape that
    # carries no observation of its own (an opening row observes nothing), so
    # nothing but the group's run boundary keeps them apart: adjacent, same
    # entity, same mutation, same member set, they are precisely what the
    # collapse decision admits, and they would settle as ONE two-entry insert
    # if the group did not close the run it interrupted.
    group = _version_group(
        "Account", "update", "id", [(9, 1)], [WriteAssignment("Account.balance", Decimal("5.00"))]
    )
    buffer: list[_TestBufferItem] = [
        KeyedWrite("insert", "Account", ({"id": 1, "owner": "Ada", "balance": Decimal("5.00")},)),
        group,
        KeyedWrite("insert", "Account", ({"id": 2, "owner": "Bo", "balance": Decimal("5.00")},)),
    ]
    plan = _plan(buffer, _ACCOUNT)
    inserts = [step for step in plan.steps if isinstance(step, PlannedInsert)]
    assert [_insert_rows(step)[0]["id"] for step in inserts] == [1, 2]
    assert all(len(step.entries) == 1 for step in inserts)


def test_batching_never_touches_a_predicate_write() -> None:
    predicate = PredicateWrite(
        "delete",
        PredicateSelection(
            "Wallet", predicate_algebra.Comparison("lessThan", "Wallet.balance", "1.00")
        ),
    )
    plan = _plan([predicate], _WALLET)
    (step,) = plan.steps
    assert isinstance(step, PlannedDelete)
    assert isinstance(step.target, ValidatedMutationSelection)
    assert step.target.predicate.authored == predicate_algebra.Comparison(
        "lessThan", "Wallet.balance", "1.00"
    )


# --------------------------------------------------------------------------- #
# Materialized Write Group (`m-unit-work` "Materialized Write Groups", ADR    #
# 0014): exempt from coalescing and from batching; dependency ordering moves  #
# it as ONE block; settles lazily into one `PlannedWrite` per resolved row.   #
# --------------------------------------------------------------------------- #
def test_materialized_group_settles_to_one_step_per_resolved_row_in_order() -> None:
    group = _version_group(
        "Account",
        "update",
        "id",
        [(1, 1), (2, 1)],
        [WriteAssignment("Account.balance", Decimal("10.00"))],
    )
    plan = _plan([group], _ACCOUNT)
    assert len(plan.steps) == 2
    ids: list[object] = []
    for step in plan.steps:
        assert isinstance(step, PlannedUpdate)
        ids.append(_single_key(step))
    assert ids == [1, 2]


@pytest.mark.parametrize("mutation", ["updateUntil", "terminate", "terminateUntil"])
def test_materialized_group_refuses_a_milestone_verb_on_a_non_temporal_target(
    mutation: PredicateMutation,
) -> None:
    # A group reaches settlement already resolved, so the verb it carries is
    # measured against the target here or nowhere: `Account` is versioned and
    # NON-temporal, so a bounded `updateUntil` has no Valid-Time window to
    # write and nothing to close. Settled as an ordinary versioned update it
    # would consume each row's observed version while silently discarding the
    # bounds — the same mismatch an addressed keyed write is refused for.
    assignments = (
        [WriteAssignment("Account.balance", Decimal("5.00"))] if mutation == "updateUntil" else []
    )
    with pytest.raises(WriteInstructionError, match="Non-temporal objects like 'Account'"):
        _version_group("Account", mutation, "id", [(1, 1)], assignments)


def test_materialized_group_rejects_an_authored_version_assignment() -> None:
    # A materializing predicate update's own assignment can never author the
    # version attribute — the version is framework-owned end to end (`m-opt-
    # lock` "Version values are framework-owned") — checked once for the
    # whole group, since every resolved row shares the same assignment.
    with pytest.raises(WriteInstructionError, match="framework-owned"):
        _version_group("Account", "update", "id", [(1, 1)], [WriteAssignment("Account.version", 9)])


def test_materialized_group_is_exempt_from_same_object_coalescing() -> None:
    # A group's own row is never folded with an unrelated buffered insert of
    # the SAME object identity — it passes through coalesce opaque.
    insert = KeyedWrite(
        "insert", "Account", ({"id": 1, "owner": "Ada", "balance": Decimal("1.00")},)
    )
    group = _version_group(
        "Account", "update", "id", [(1, 1)], [WriteAssignment("Account.balance", Decimal("2.00"))]
    )
    plan = _plan([insert, group], _ACCOUNT)
    assert _shape(plan) == [("insert", "Account"), ("update", "Account")]


def test_materialized_group_is_exempt_from_batching() -> None:
    # A group's OWN member rows never re-batch into a multi-row instruction,
    # even when they would otherwise be eligible (adjacent, same entity/
    # mutation, uniform values) — each per-row gated write stays its own step
    # (`m-batch-write`).
    group = _version_group(
        "Account",
        "update",
        "id",
        [(1, 1), (2, 1)],
        [WriteAssignment("Account.balance", Decimal("5.00"))],
    )
    plan = _plan([group], _ACCOUNT)
    assert len(plan.steps) == 2


def test_materialized_group_moves_as_one_block_under_dependency_ordering() -> None:
    # The group is ONE ordering unit: its rows stay ADJACENT and in their OWN
    # resolved-row order, and the whole block moves relative to the OTHER
    # buffered instruction, which the caller buffered FIRST yet which settles
    # first only because ordering partitions by mutation. A delete group needs
    # no uniform assignment across its rows, so it isolates the ordering
    # property from the collapse decision. The target is versioned because a
    # group carries observation columns, which only an observation-entitled
    # target may hold; FK-rank ordering is proven on its own above.
    group = _version_group("Account", "delete", "id", [(2, 1), (1, 1)])
    other = KeyedWrite(
        "insert", "Account", ({"id": 10, "owner": "Ada", "balance": Decimal("1.00")},)
    )
    plan = _plan([group, other], _ACCOUNT)
    shapes: list[tuple[str, object]] = []
    for step in plan.steps:
        if isinstance(step, PlannedInsert):
            shapes.append(("insert", _insert_rows(step)[0]["id"]))
        else:
            assert isinstance(step, PlannedDelete)
            shapes.append(("delete", _single_key(step)))
    # inserts before updates/deletes — the canonical INSERT -> UPDATE -> DELETE
    # order; the group's OWN two rows stay adjacent and in their OWN resolved
    # order (2 then 1), never re-sorted by id.
    assert shapes == [("insert", 10), ("delete", 2), ("delete", 1)]


# --------------------------------------------------------------------------- #
# Transaction Instant laziness through the full pipeline (ADR 0010).          #
# --------------------------------------------------------------------------- #
def test_planning_never_captures_the_transaction_instant_for_canceled_work() -> None:
    # The stage order's whole point: coalescing cancels the pair before any
    # surviving write could need a Transaction-Time boundary, so the clock
    # behind the holder the request carries is never consulted.
    clock = CountingClock([dt.datetime(2024, 6, 1, tzinfo=dt.UTC)])
    insert = KeyedWrite(
        "insert", "Account", ({"id": 1, "owner": "Ada", "balance": Decimal("1.00")},)
    )
    delete = KeyedWrite("delete", "Account", ({"id": 1},))
    plan = _plan([insert, delete], _ACCOUNT, tx_instant=TransactionInstant(clock))
    assert len(plan.steps) == 0
    assert clock.calls == 0


def test_planning_captures_the_transaction_instant_only_for_surviving_temporal_work() -> None:
    clock = CountingClock([dt.datetime(2024, 6, 1, tzinfo=dt.UTC)])
    non_temporal = KeyedWrite(
        "insert", "Wallet", ({"id": 1, "owner": "Ada", "balance": Decimal("1.00")},)
    )
    plan = _plan([non_temporal], _WALLET, tx_instant=TransactionInstant(clock))
    assert len(plan.steps) == 1
    assert clock.calls == 0

    temporal_clock = CountingClock([dt.datetime(2024, 6, 1, tzinfo=dt.UTC)])
    temporal = KeyedWrite(
        "insert", "Balance", ({"id": 1, "acctNum": "A", "value": Decimal("1.00")},)
    )
    plan = _plan([temporal], _BALANCE, tx_instant=TransactionInstant(temporal_clock))
    (step,) = plan.steps
    assert isinstance(step, PlannedInsert)
    assert _insert_rows(step)[0]["txStart"] == dt.datetime(2024, 6, 1, tzinfo=dt.UTC)
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
        "update",
        "Position",
        ({"id": 5, "value": Decimal("42.0")},),
        valid_from=dt.datetime(2024, 3, 1, tzinfo=dt.UTC),
    )
    key_ = object_key(position_update, _POSITION)
    assert key_ is not None
    buffer: list[_TestBufferItem] = [
        KeyedWrite("insert", "Wallet", ({"id": 1, "owner": "Ada", "balance": Decimal("1.00")},)),
        position_update,
        KeyedWrite("delete", "Wallet", ({"id": 2},)),
    ]
    model = formed(
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
                "value": Decimal("1.0"),
                "validStart": "2024-01-01T00:00:00+00:00",
                "validEnd": "infinity",
                "txStart": "2024-01-01T00:00:00+00:00",
                "txEnd": "infinity",
            }
        )
    )


# --------------------------------------------------------------------------- #
# One temporal settlement for both representations: the eagerly settled        #
# instruction and the Materialized Write Group decide the same facts and emit  #
# from them the same way, so the two cannot drift.                             #
# --------------------------------------------------------------------------- #
_BALANCE_PREDECESSOR: dict[str, object] = {
    "id": 1,
    "acctNum": "A",
    "value": Decimal("1.00"),
    "txStart": "2024-01-01T00:00:00+00:00",
    "txEnd": "infinity",
}


def _one_row_temporal_group(assigned: Decimal) -> MaterializedWriteGroup:
    """A Materialized Write Group resolving the one row
    :data:`_BALANCE_PREDECESSOR` describes, under the same update."""
    return temporal_group(
        PredicateWrite(
            "update",
            PredicateSelection(
                "Balance", predicate_algebra.Comparison("lessThan", "Balance.value", "1000000.00")
            ),
            assignments=(WriteAssignment("Balance.value", assigned),),
        ),
        _BALANCE,
        [_BALANCE_PREDECESSOR],
    )


def test_one_temporal_row_settles_identically_addressed_and_materialized() -> None:
    # The same observed row, the same authored change, the same instant, and
    # the same concurrency mode, reaching settlement through its two
    # representations: an addressed keyed write settled eagerly, and a
    # one-row Materialized Write Group settled into a segment that emits on
    # demand. Every temporal fact — the topology's close cause, the axis the
    # gate binds, the successors and their represented state, the resolved
    # instant — is decided in one place for both, so the two plans must be
    # equal step for step. A drift between the arms is precisely what a
    # second derivation site would produce.
    assigned = Decimal("9.00")
    addressed = KeyedWrite("update", "Balance", ({"id": 1, "value": assigned},))
    key_ = object_key(addressed, _BALANCE)
    assert key_ is not None
    eager = _plan(
        [addressed],
        _BALANCE,
        observations={
            key_: TemporalObservation(predecessor=PredecessorRow(members=_BALANCE_PREDECESSOR))
        },
        concurrency="optimistic",
        tx_instant=instant_at("2024-06-01T00:00:00+00:00"),
    )
    materialized = _plan(
        [_one_row_temporal_group(assigned)],
        _BALANCE,
        concurrency="optimistic",
        tx_instant=instant_at("2024-06-01T00:00:00+00:00"),
    )
    assert _shape(eager) == [("close", "Balance"), ("insert", "Balance")]
    assert list(materialized.steps) == list(eager.steps)


def test_one_versioned_row_settles_identically_addressed_and_materialized() -> None:
    # The non-temporal counterpart. The same observed row, the same authored
    # value, and the same concurrency mode, reaching settlement through its two
    # representations: an addressed keyed update settled eagerly, and a one-row
    # Materialized Write Group settled into a segment that emits on demand. Every
    # non-temporal fact — the family-effective key the target addresses by, the
    # version Attribute, the gate the observation binds, the advanced version the
    # update assigns, and how a shortfall classifies — is decided in one place for
    # both, so a single addressed row and a single resolved row must agree
    # exactly. Their CARDINALITY is the one thing they do not share, and it is
    # not in evidence here: both plans carry one step over one key.
    assigned = Decimal("5.00")
    addressed = KeyedWrite("update", "Account", ({"id": 9, "balance": assigned},))
    key_ = object_key(addressed, _ACCOUNT)
    assert key_ is not None
    eager = _plan(
        [addressed],
        _ACCOUNT,
        observations={key_: VersionObservation(observed_version=1)},
        concurrency="optimistic",
    )
    materialized = _plan(
        [
            _version_group(
                "Account", "update", "id", [(9, 1)], [WriteAssignment("Account.balance", assigned)]
            )
        ],
        _ACCOUNT,
        concurrency="optimistic",
    )
    (settled,) = eager.steps
    assert isinstance(settled, PlannedUpdate)
    assert list(materialized.steps) == [settled]


# --------------------------------------------------------------------------- #
# The prepared path resolves its targets by reference: every write reaching   #
# `finalize` carries exact target Metadata, so no flush pays an entity-       #
# spelling scan.                                                              #
# --------------------------------------------------------------------------- #
def test_a_prepared_finalize_resolves_targets_without_any_entity_spelling_scan(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Spelling resolution is raw authored input's own branch, and the buffer a
    # flush plans holds none: every arm settlement forks on is driven here —
    # keyed insert, observed versioned update, readless predicate write,
    # Materialized Write Group, and a bitemporal mutation — with the scan wired
    # to fail, so reaching it at all is the failure rather than a slow path.
    model = formed(
        DescriptorMetamodel(
            entities=(
                *_MODELS["wallet"].entities,
                *_MODELS["account"].entities,
                *_MODELS["position"].entities,
            )
        )
    )
    account_update = KeyedWrite("update", "Account", ({"id": 3, "balance": Decimal("7.00")},))
    position_update = KeyedWrite(
        "update",
        "Position",
        ({"id": 5, "value": Decimal("42.0")},),
        valid_from=dt.datetime(2024, 3, 1, tzinfo=dt.UTC),
    )
    account_key = object_key(account_update, model)
    position_key = object_key(position_update, model)
    assert account_key is not None and position_key is not None
    buffer: list[_TestBufferItem] = [
        KeyedWrite("insert", "Wallet", ({"id": 1, "owner": "Ada", "balance": Decimal("1.00")},)),
        account_update,
        position_update,
        _version_group(
            "Account",
            "update",
            "id",
            [(9, 1)],
            [WriteAssignment("Account.balance", Decimal("5.00"))],
            model=model,
        ),
        PredicateWrite(
            "delete",
            PredicateSelection("Wallet", predicate_algebra.Comparison("eq", "Wallet.id", 2)),
        ),
    ]
    prepared = observed_buffer(
        buffer,
        model,
        {
            account_key: VersionObservation(observed_version=4),
            position_key: _bitemporal_observation(),
        },
    )

    def refuse(_model: Metamodel, spelling: str) -> None:
        raise AssertionError(f"the prepared path resolved {spelling!r} by scanning the model")

    # Both bindings a flush could reach the model's spelling rule through: key
    # derivation's, and the refusal that names an Entity the model does not
    # declare.
    monkeypatch.setattr(planner_module, "entity_by_name", refuse)
    monkeypatch.setattr(write_settlement_module, "entity_by_name", refuse)
    plan = (
        build_write_planner(model)
        .finalize(
            PlanningRequest(
                actor_identity=TEST_ACTOR_IDENTITY,
                transaction_instant=instant_at("2024-06-01T00:00:00+00:00"),
                concurrency="optimistic",
                buffered_writes=prepared,
            )
        )
        .plan
    )
    kinds = [_step_mutation(step) for step in plan.steps]
    assert kinds.count("insert") >= 2  # the Wallet insert, plus the bitemporal successors
    assert "close" in kinds
    assert kinds.count("update") == 2  # the addressed Account update and the group's one row
    assert kinds[-1] == "delete"  # the readless predicate write, held at the barrier


# --------------------------------------------------------------------------- #
# Settlement reads a temporal mutation's Temporal Shape once, at dispatch, and #
# every later decision reads that same family-owned object.                    #
# --------------------------------------------------------------------------- #
_TEMPORAL_FAMILIES = formed(
    DescriptorMetamodel(
        entities=(
            *_MODELS["balance"].entities,
            *_MODELS["quote"].entities,
            *_MODELS["rate"].entities,
        )
    )
)
_OPENED = dt.datetime(2024, 1, 1, tzinfo=dt.UTC)


@dataclass(frozen=True, slots=True)
class _RecordingTopology:
    """The production topology dispatch, recording each shape it was handed."""

    shapes: list[object]

    def topology(
        self,
        shape: temporal_read.TransactionTimeOnly | temporal_read.Bitemporal,
        mutation: str,
    ) -> MilestoneTopology:
        self.shapes.append(shape)
        if isinstance(shape, temporal_read.Bitemporal):
            return bitemp_write.RECTANGLE_SPLIT.topology(mutation)
        return txtime_write.MILESTONE_CHAIN.topology(mutation)


def _temporal_family_writes() -> list[BufferItem]:
    """Observed updates of an inherited Transaction-Time-Only and an inherited
    Bitemporal position, then a three-row group over a standalone target."""
    quote = KeyedWrite("update", "SpotQuote", ({"id": 1, "price": Decimal("2.00")},))
    rate = KeyedWrite(
        "update",
        "DepositRate",
        ({"id": 2, "amount": Decimal("3.00")},),
        valid_from=dt.datetime(2024, 3, 1, tzinfo=dt.UTC),
    )
    transaction_time = {"txStart": _OPENED, "txEnd": "infinity"}
    observed = {
        corpus_object_key("SpotQuote", ("id", 1)): {
            "id": 1,
            "price": Decimal("1.00"),
            "symbol": "Q",
            **transaction_time,
        },
        corpus_object_key("DepositRate", ("id", 2)): {
            "id": 2,
            "amount": Decimal("1.00"),
            "grade": "A",
            "validStart": _OPENED,
            "validEnd": "infinity",
            **transaction_time,
        },
    }
    group = temporal_group(
        PredicateWrite(
            "terminate",
            PredicateSelection(
                "Balance", predicate_algebra.Comparison("lessThan", "Balance.value", "1000000.00")
            ),
        ),
        _TEMPORAL_FAMILIES,
        [
            {"id": row, "acctNum": "B", "value": Decimal("1.00"), **transaction_time}
            for row in (10, 11, 12)
        ],
    )
    return [
        *observed_buffer(
            [quote, rate],
            _TEMPORAL_FAMILIES,
            {
                key_: TemporalObservation(predecessor=PredecessorRow(members=members))
                for key_, members in observed.items()
            },
        ),
        group,
    ]


def test_settlement_reads_each_temporal_mutations_family_shape_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # One read per addressed write and one per group, however many rows the group
    # resolved, and none on step access: the shape dispatch read is the one every
    # later decision — topology, close address, gate basis, successor binding —
    # reuses. What those decisions receive is the family's own interned object,
    # so an inherited position hands on its root's shape rather than an equal
    # rebuilt one.
    facet = temporal_read.view(_TEMPORAL_FAMILIES)
    owners = {
        name: facet.shape(corpus_entity(name)) for name in ("SpotQuote", "DepositRate", "Balance")
    }
    buffered = _temporal_family_writes()
    shapes: list[object] = []
    monkeypatch.setattr(
        planning_composition, "_TemporalAdapter", lambda: _RecordingTopology(shapes)
    )
    planner = build_write_planner(_TEMPORAL_FAMILIES)
    reads: list[str] = []
    read_shape = type(facet).shape

    def counting(self: temporal_read.TemporalFacet, entity: EntityIdentity) -> object:
        reads.append(entity.name)
        return read_shape(self, entity)

    monkeypatch.setattr(type(facet), "shape", counting)
    plan = planner.finalize(
        PlanningRequest(
            actor_identity=TEST_ACTOR_IDENTITY,
            transaction_instant=instant_at("2024-06-01T00:00:00+00:00"),
            concurrency="optimistic",
            buffered_writes=buffered,
        )
    ).plan
    assert reads == ["SpotQuote", "DepositRate", "Balance"]
    _ = list(plan.steps)
    _ = plan.steps[len(plan.steps) - 1]
    assert reads == ["SpotQuote", "DepositRate", "Balance"]
    assert all(shape is owners[name] for shape, name in zip(shapes, reads, strict=True))
    group_segment = plan.steps.segments[-1]
    assert cast("Any", group_segment).facts.shape is owners["Balance"]
    assert len(group_segment) == 3


@dataclass(frozen=True, slots=True)
class _ValidTimeGatedTopology:
    """The Bitemporal topology with its close gated on the Valid-Time axis."""

    def topology(
        self,
        shape: temporal_read.TransactionTimeOnly | temporal_read.Bitemporal,
        mutation: str,
    ) -> MilestoneTopology:
        topology = bitemp_write.RECTANGLE_SPLIT.topology(mutation)
        assert topology.closure is not None
        return dataclasses.replace(
            topology,
            closure=dataclasses.replace(topology.closure, gate_basis=TemporalDimension.VALID_TIME),
        )


def test_a_close_gates_on_the_axis_its_topology_names(monkeypatch: pytest.MonkeyPatch) -> None:
    # The gate basis is the topology's decision, and settlement binds the start
    # of whichever axis of the family's shape it names.
    update = KeyedWrite(
        "update",
        "Position",
        ({"id": 5, "value": Decimal("42.0")},),
        valid_from=dt.datetime(2024, 3, 1, tzinfo=dt.UTC),
    )
    key_ = object_key(update, _POSITION)
    assert key_ is not None
    monkeypatch.setattr(planning_composition, "_TemporalAdapter", _ValidTimeGatedTopology)
    plan = _plan(
        [update],
        _POSITION,
        observations={key_: _bitemporal_observation()},
        concurrency="optimistic",
        tx_instant=instant_at("2024-06-01T00:00:00+00:00"),
    )
    close = plan.steps[0]
    assert isinstance(close, PlannedClose)
    assert isinstance(close.concurrency, TemporalGate)
    assert close.concurrency.start_attribute.name == "validStart"
    assert close.concurrency.observed_start == "2024-01-01T00:00:00+00:00"


# --------------------------------------------------------------------------- #
# Settlement reads the whole ordered sequence: eager runs pack around a        #
# Materialized Write Group's own segment, provenance reaches the eager steps   #
# alone, and the claims answered are the surviving carriers' own.              #
# --------------------------------------------------------------------------- #
def _wallet_and_account() -> Metamodel:
    return formed(
        DescriptorMetamodel(entities=(*_MODELS["wallet"].entities, *_MODELS["account"].entities))
    )


def _eager_group_eager(model: Metamodel) -> list[_TestBufferItem]:
    """An update, a Materialized Write Group, and an update — one region, one
    verb bucket, so dependency ordering leaves the three in buffer order."""
    return [
        KeyedWrite("update", "Wallet", ({"id": 1, "balance": Decimal("2.00")},)),
        _version_group(
            "Account",
            "update",
            "id",
            [(9, 1)],
            [WriteAssignment("Account.balance", Decimal("5.00"))],
            model=model,
        ),
        KeyedWrite("update", "Wallet", ({"id": 2, "balance": Decimal("3.00")},)),
    ]


def test_eager_runs_pack_on_each_side_of_a_groups_own_segment() -> None:
    # Packing is a property of ADJACENCY, which is why settlement reads the whole
    # ordered sequence rather than one item at a time: a run of eagerly settled
    # steps stays one segment, and a Materialized Write Group always occupies its
    # own, so a group between two eager writes yields three segments rather than
    # one per input.
    model = _wallet_and_account()
    plan = _plan(_eager_group_eager(model), model)
    assert [len(segment) for segment in plan.steps.segments] == [1, 1, 1]
    assert _shape(plan) == [("update", "Wallet"), ("update", "Account"), ("update", "Wallet")]
    # The group's own segment rebuilds its row on demand; the eager ones do not.
    assert plan.steps[1] == plan.steps[1]
    assert plan.steps[1] is not plan.steps[1]
    assert plan.steps[0] is plan.steps[0]


@dataclass(frozen=True, slots=True)
class _CountingAudit:
    """The neutral strategy, recording each step it was handed."""

    decorated: list[PlannedWrite]
    actors: list[ActorIdentity]

    def decorate(
        self,
        step: PlannedWrite,
        *,
        actor_identity: ActorIdentity,
        transaction_instant: TransactionInstant,
    ) -> PlannedWrite:
        self.decorated.append(step)
        self.actors.append(actor_identity)
        return step


def test_provenance_reaches_every_eager_step_once_and_no_materialized_row(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Decoration follows topology and precedes freezing, and its boundary is the
    # eager arm: a Materialized Write Group's rows are rebuilt on demand from a
    # segment holding no strategy and no unevaluated instant, so they cannot be
    # decorated one at a time and are not (ADR 0037; `m-unit-work`). A neutral
    # strategy hands back the step it was given, so each eager step of the frozen
    # plan is the IDENTICAL object settlement produced — decoration sits between
    # settling a step and packing it, and packing copies nothing.
    audit = _CountingAudit([], [])
    monkeypatch.setattr(planning_composition, "NO_AUDIT", audit)
    model = _wallet_and_account()
    plan = (
        build_write_planner(model)
        .finalize(
            PlanningRequest(
                actor_identity=TEST_ACTOR_IDENTITY,
                transaction_instant=_INSTANT,
                concurrency="locking",
                buffered_writes=observed_buffer(_eager_group_eager(model), model, None),
            )
        )
        .plan
    )
    assert len(plan.steps) == 3
    assert len(audit.decorated) == 2
    assert audit.actors == [TEST_ACTOR_IDENTITY, TEST_ACTOR_IDENTITY]
    assert plan.steps[0] is audit.decorated[0]
    assert plan.steps[2] is audit.decorated[1]
    assert all(decorated is not plan.steps[1] for decorated in audit.decorated)


def test_provenance_decorates_the_topology_temporal_expansion_produced(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Decoration follows TOPOLOGY, so what a temporal mutation hands the strategy
    # is the run stage 7 expanded it into rather than the one update the buffer
    # carried: the close reaches the strategy first, its chained successors reach
    # it in their already-decided order, and no step of the frozen plan reaches it
    # twice or not at all.
    audit = _CountingAudit([], [])
    monkeypatch.setattr(planning_composition, "NO_AUDIT", audit)
    update = KeyedWrite(
        "update",
        "Position",
        ({"id": 5, "value": Decimal("42.0")},),
        valid_from=dt.datetime(2024, 3, 1, tzinfo=dt.UTC),
    )
    key_ = object_key(update, _POSITION)
    assert key_ is not None
    plan = _plan(
        [update],
        _POSITION,
        observations={key_: _bitemporal_observation()},
        tx_instant=instant_at("2024-06-01T00:00:00+00:00"),
    )
    steps = list(plan.steps)
    assert isinstance(steps[0], PlannedClose)
    assert len(steps) >= 2
    assert all(isinstance(step, PlannedInsert) for step in steps[1:])
    assert all(step is decorated for step, decorated in zip(steps, audit.decorated, strict=True))


def test_only_surviving_writes_contribute_claims_and_a_shared_claim_answers_once() -> None:
    # Consumption records a fact about an observed state, so a flush spends one
    # claim once however many surviving writes settled against it — here two,
    # because a destruction and an assignment of one state are a pair no verb
    # admitted as combinable and both are left standing. A carrier the earlier
    # stages retire takes its claim out of the flush with it: the key-only update
    # below is known no-op work, eliminated at stage 2, and never settled, so its
    # claim is absent by ABSENCE rather than by a second filter.
    observation = VersionObservation(observed_version=7)
    shared = RetainedObservation(
        VersionedStateKey(corpus_object_key("Account", ("id", 1)), 7), observation, None
    )
    retired_observation = VersionObservation(observed_version=4)
    retired = RetainedObservation(
        VersionedStateKey(corpus_object_key("Account", ("id", 2)), 4), retired_observation, None
    )
    buffer = [
        _observed(KeyedWrite("delete", "Account", ({"id": 1},)), observation, claim=shared),
        _observed(
            KeyedWrite("update", "Account", ({"id": 1, "balance": Decimal("9.00")},)),
            observation,
            claim=shared,
        ),
        _observed(
            KeyedWrite("update", "Account", ({"id": 2},)), retired_observation, claim=retired
        ),
    ]
    finalized = build_write_planner(_ACCOUNT).finalize(
        PlanningRequest(
            actor_identity=TEST_ACTOR_IDENTITY,
            transaction_instant=_INSTANT,
            concurrency="locking",
            buffered_writes=buffer,
        )
    )
    assert [_step_mutation(step) for step in finalized.plan.steps] == ["update", "delete"]
    assert finalized.claims == (shared,)


# --------------------------------------------------------------------------- #
# Settlement's structural refusals are TOTAL: they judge the prepared         #
# carrier handed across the seam rather than the ingress that built one, so   #
# a shape no preparation path produces is refused here rather than settled.   #
# Each carrier below is derived from a prepared write, which is the only      #
# input settlement takes.                                                     #
# --------------------------------------------------------------------------- #
def _derived(write: KeyedWrite, model: Metamodel, **changes: object) -> PreparedKeyedWrite:
    """A prepared keyed write carrying a shape no ingress would have produced."""
    return dataclasses.replace(_prepared_keyed(write, model), **changes)


def test_a_plural_temporal_instruction_is_refused_at_settlement() -> None:
    plural = _derived(
        KeyedWrite("update", "Balance", ({"id": 1, "value": Decimal("1.00")},)),
        _BALANCE,
        rows=({"id": 1, "value": Decimal("1.00")}, {"id": 2, "value": Decimal("2.00")}),
    )
    with pytest.raises(WritePlanningError, match="multi-row temporal 'update' on 'Balance'"):
        _plan([plural], _BALANCE)


def test_a_keyed_milestone_verb_on_a_non_temporal_target_is_refused_at_settlement() -> None:
    bounded = _derived(
        KeyedWrite("update", "Wallet", ({"id": 1, "balance": Decimal("1.00")},)),
        _WALLET,
        mutation="updateUntil",
    )
    with pytest.raises(WritePlanningError, match="Non-temporal objects like 'Wallet'"):
        _plan([bounded], _WALLET)


def test_a_readless_predicate_milestone_verb_is_refused_at_settlement() -> None:
    deletion = prepare_typed_write(
        PredicateWrite(
            "delete",
            PredicateSelection("Wallet", predicate_algebra.Comparison("eq", "Wallet.id", 1)),
        ),
        _WALLET,
    )
    assert isinstance(deletion, PreparedPredicateWrite)
    with pytest.raises(WritePlanningError, match="a readless predicate 'terminate'"):
        _plan([dataclasses.replace(deletion, mutation="terminate")], _WALLET)


def test_a_materialized_group_authoring_the_version_is_refused_at_settlement() -> None:
    group = _version_group(
        "Account", "update", "id", [(1, 1)], [WriteAssignment("Account.balance", Decimal("5.00"))]
    )
    entity = group.mutation.selection.target
    position = inheritance.view(_ACCOUNT).entity(entity.identity)
    assert position is not None
    version = position.applicable_attribute("version")
    assert version is not None
    authored = MaterializedWriteGroup(
        mutation=dataclasses.replace(
            group.mutation, managed_assignments=(PreparedAssignment(version, 9),)
        ),
        evidence=group.evidence,
    )
    with pytest.raises(CallerAuthoredVersionError, match="framework-owned"):
        _plan([authored], _ACCOUNT)


def test_a_row_naming_a_member_outside_the_family_is_refused_at_settlement() -> None:
    stray = _derived(
        KeyedWrite("insert", "Wallet", ({"id": 1, "owner": "Ada", "balance": Decimal("1.00")},)),
        _WALLET,
        rows=({"id": 1, "owner": "Ada", "balance": Decimal("1.00"), "nickname": "w"},),
    )
    with pytest.raises(WritePlanningError, match="names 'nickname', which is not a member"):
        _plan([stray], _WALLET)


def test_a_many_keyed_mapping_cell_is_an_ordinary_literal_not_a_computed_marker() -> None:
    # A DB-computed marker is classified by SHAPE — a ONE-key mapping naming a
    # recognized kind — so a mapping carrying more than one key is a value the
    # row writes rather than an allocation the statement must express.
    document = {"computed": "maxPlusOne", "note": "not a marker"}
    carried = _derived(
        KeyedWrite("insert", "Wallet", ({"id": 1, "owner": "Ada", "balance": Decimal("1.00")},)),
        _WALLET,
        rows=({"id": 1, "owner": document, "balance": Decimal("1.00")},),
    )
    (step,) = _plan([carried], _WALLET).steps
    assert _insert_rows(step)[0]["owner"] == document


# --------------------------------------------------------------------------- #
# A temporal group's step access builds exactly the one step it names, and    #
# only a carried or changed successor reads a Predecessor Row.                 #
# --------------------------------------------------------------------------- #
_OPENED_AT = dt.datetime(2024, 1, 1, tzinfo=dt.UTC)
_WINDOW_FROM = dt.datetime(2024, 3, 1, tzinfo=dt.UTC)
_WINDOW_UNTIL = dt.datetime(2024, 9, 1, tzinfo=dt.UTC)


def _temporal_topology_group(
    model: Metamodel, entity: str, mutation: PredicateMutation, rows: int = 3
) -> MaterializedWriteGroup:
    bitemporal = entity == "Position"
    bounded = mutation.endswith("Until")
    bounds: tuple[dt.datetime, ...] = (
        (_WINDOW_FROM, _WINDOW_UNTIL) if bounded else (_WINDOW_FROM,) if bitemporal else ()
    )
    axes: dict[str, object] = {"validStart": _OPENED_AT, "validEnd": INFINITY} if bitemporal else {}
    return temporal_group(
        PredicateWrite(
            mutation,
            PredicateSelection(
                entity, predicate_algebra.Comparison("lessThan", f"{entity}.value", "100.00")
            ),
            (WriteAssignment(f"{entity}.value", Decimal("9.00")),)
            if mutation.startswith("update")
            else (),
            *bounds,
        ),
        model,
        [
            {
                "id": key,
                "acctNum": "A",
                "value": Decimal("1.00"),
                **axes,
                "txStart": _OPENED_AT,
                "txEnd": INFINITY,
            }
            for key in range(1, rows + 1)
        ],
    )


class _Constructions:
    """Counts the planned steps and Predecessor Rows built from now on."""

    def __init__(self, monkeypatch: pytest.MonkeyPatch) -> None:
        self.steps = 0
        self.predecessors = 0
        for step_type in (PlannedClose, PlannedInsert):
            original = step_type.__init__

            def counting(
                step: object, *args: object, _original: Any = original, **kwargs: object
            ) -> None:
                self.steps += 1
                _original(step, *args, **kwargs)

            monkeypatch.setattr(step_type, "__init__", counting)
        over_row = PredecessorRow.over_row

        def adopted(*args: Any) -> PredecessorRow:
            self.predecessors += 1
            return over_row(*args)

        monkeypatch.setattr(PredecessorRow, "over_row", adopted)


@pytest.mark.parametrize(
    ("entity", "mutation", "steps_per_row"),
    [
        ("Balance", "update", 2),
        ("Balance", "terminate", 1),
        ("Balance", "updateUntil", 2),
        ("Balance", "terminateUntil", 1),
        ("Position", "update", 3),
        ("Position", "terminate", 2),
        ("Position", "updateUntil", 4),
        ("Position", "terminateUntil", 3),
    ],
)
def test_indexing_a_temporal_group_constructs_only_the_requested_step(
    monkeypatch: pytest.MonkeyPatch, entity: str, mutation: PredicateMutation, steps_per_row: int
) -> None:
    model = _BALANCE if entity == "Balance" else _POSITION
    plan = _plan([_temporal_topology_group(model, entity, mutation)], model)
    settled = list(plan.steps)
    assert len(settled) == 3 * steps_per_row
    constructed = _Constructions(monkeypatch)

    for index in range(len(settled)):
        assert plan.steps[index] == settled[index]
    assert constructed.steps == len(settled)
    assert constructed.predecessors == sum(isinstance(step, PlannedInsert) for step in settled)

    constructed.steps = constructed.predecessors = 0
    last, first = len(settled) - 1, 0
    for index in (last, first, last):
        assert plan.steps[index] == settled[index]
    assert constructed.steps == 3
    assert constructed.predecessors == 2 * isinstance(settled[last], PlannedInsert)


def test_a_temporal_groups_marker_no_opened_row_expresses_is_refused_while_planning() -> None:
    group = temporal_group(
        PredicateWrite(
            "update",
            PredicateSelection(
                "Balance", predicate_algebra.Comparison("lessThan", "Balance.value", "100.00")
            ),
            (WriteAssignment("Balance.acctNum", {"increment": 1}),),
        ),
        _BALANCE,
        [
            {
                "id": 1,
                "acctNum": "A",
                "value": Decimal("1.00"),
                "txStart": _OPENED_AT,
                "txEnd": INFINITY,
            }
        ],
    )
    with pytest.raises(WritePlanningError, match="not recognized for insert planning"):
        _plan([group], _BALANCE)


# --------------------------------------------------------------------------- #
# Effective change is established by the producer: a surviving row of a       #
# multi-assignment group carries the members it restores.                     #
# --------------------------------------------------------------------------- #
def _comparisons(monkeypatch: pytest.MonkeyPatch) -> dict[str, int]:
    calls = {"prepared": 0, "compared": 0}
    prepare = prepare_effective_change
    effective_positions = PreparedEffectiveChange.effective_positions

    def preparing(*args: Any, **kwargs: Any) -> PreparedEffectiveChange:
        calls["prepared"] += 1
        return prepare(*args, **kwargs)

    def comparing(change: PreparedEffectiveChange, row: tuple[object, ...]) -> Any:
        calls["compared"] += 1
        return effective_positions(change, row)

    monkeypatch.setattr(write_settlement_module, "prepare_effective_change", preparing)
    monkeypatch.setattr(PreparedEffectiveChange, "effective_positions", comparing)
    return calls


def _position_update(*assignments: WriteAssignment, account: str) -> MaterializedWriteGroup:
    return temporal_group(
        PredicateWrite(
            "update",
            PredicateSelection(
                "Position", predicate_algebra.Comparison("lessThan", "Position.value", "100.00")
            ),
            assignments,
            _WINDOW_FROM,
        ),
        _POSITION,
        [
            {
                "id": key,
                "acctNum": account,
                "value": Decimal("1.00"),
                "validStart": _OPENED_AT,
                "validEnd": INFINITY,
                "txStart": _OPENED_AT,
                "txEnd": INFINITY,
            }
            for key in (1, 2)
        ],
    )


def test_a_surviving_multi_assignment_row_carries_the_member_it_restores(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = _comparisons(monkeypatch)
    stored_account = "".join(("ACC", "-1"))
    group = _position_update(
        WriteAssignment("Position.acctNum", "ACC-1"),
        WriteAssignment("Position.value", Decimal("9.00")),
        account=stored_account,
    )
    assert isinstance(group.evidence, PredecessorRows)
    plan = _plan([group], _POSITION)
    assert calls == {"prepared": 1, "compared": 0}

    changed = [
        entry
        for step in plan.steps
        if isinstance(step, PlannedInsert)
        for entry in step.entries
        if isinstance(entry.origin, ChangedFrom)
    ]
    assert len(changed) == 2
    assert calls == {"prepared": 1, "compared": 2}
    for entry in changed:
        values = _row_values(entry.row)
        account = next(ident for ident in entry.row.attributes if ident.name == "acctNum")
        assert entry.row.attributes[account] is stored_account
        origin = cast("ChangedFrom", entry.origin)
        assert origin.predecessor.carries(account, entry.row.attributes[account])
        assert values["value"] == Decimal("9.00")


def test_single_assignment_groups_and_keyed_writes_are_not_compared_again_at_settlement(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = _comparisons(monkeypatch)
    group = _position_update(WriteAssignment("Position.value", Decimal("9.00")), account="A")
    list(_plan([group], _POSITION).steps)
    assert calls == {"prepared": 0, "compared": 0}

    addressed = KeyedWrite("update", "Balance", ({"id": 1, "value": Decimal("9.00")},))
    key_ = object_key(addressed, _BALANCE)
    assert key_ is not None
    list(
        _plan(
            [addressed],
            _BALANCE,
            observations={
                key_: TemporalObservation(predecessor=PredecessorRow(members=_BALANCE_PREDECESSOR))
            },
        ).steps
    )
    assert calls == {"prepared": 0, "compared": 0}


def test_a_keyed_predecessor_naming_a_non_member_is_refused_as_a_planning_error() -> None:
    addressed = KeyedWrite("update", "Balance", ({"id": 1, "value": Decimal("9.00")},))
    key_ = object_key(addressed, _BALANCE)
    assert key_ is not None
    predecessor = PredecessorRow(members={**_BALANCE_PREDECESSOR, "nickname": "Ada"})

    with pytest.raises(WritePlanningError, match="'Balance': predecessor member 'nickname'"):
        list(
            _plan(
                [addressed],
                _BALANCE,
                observations={key_: TemporalObservation(predecessor=predecessor)},
            ).steps
        )


def test_a_keyed_and_a_materialized_successor_lower_to_the_same_statements() -> None:
    # One retained Relational Document row changed through each producer: a
    # keyed `updateUntil` carrying its effective member alone, and a
    # materializing one over the same judged row and raw document. Both
    # successors patch the member they change and carry everything else,
    # unknown keys included, so they lower to identical statements.
    model = model_of(acquisition_support.MODEL)
    case = acquisition_support.case_named("acquisition.rows-8.document")
    target = case.prepared.selection.target
    layout = LayoutCatalog(model).entity(target.identity)
    selection = layout.member_selection
    row = positional_row(
        selection.shape,
        {
            "id": 1,
            "title": "title-1",
            "address": {"city": "Oslo", "geo": {"country": "NO"}},
            "tags": [{"label": "a"}],
            "validStart": acquisition_support.VALID_START,
            "validEnd": INFINITY,
            "txStart": acquisition_support.TX_START,
            "txEnd": INFINITY,
        },
        absent=ABSENT,
    )
    stored: dict[str, object] = {
        "title": "title-1",
        "charterCode": "NB-118",
        "address": {"city": "Oslo", "geo": {"country": "NO"}, "sealNumber": "S-4021"},
        "tags": [{"label": "a"}],
    }
    evidence = PredecessorRowsBuilder(
        selection, key_position=layout.primary_key[0], absent=ABSENT, documents=True
    )
    evidence.append(row, stored)
    sealed = evidence.seal()
    assert sealed is not None
    keyed = KeyedWrite(
        "updateUntil",
        target.identity.canonical,
        ({"id": 1, "title": acquisition_support.ASSIGNED_TITLE},),
        acquisition_support.INTERIOR_FROM,
        acquisition_support.INTERIOR_UNTIL,
    )
    key_ = object_key(keyed, model)
    assert key_ is not None
    observation = TemporalObservation(
        predecessor=PredecessorRow.over_row(selection, row, stored, ABSENT)
    )

    def lowered(plan: WritePlan) -> list[tuple[str, tuple[object, ...]]]:
        return [
            (statement.sql, tuple(statement.binds))
            for statement in (compile_write_step(step, model, POSTGRES) for step in plan.steps)
        ]

    eager = lowered(_plan([keyed], model, observations={key_: observation}))
    materialized = lowered(
        _plan([MaterializedWriteGroup(mutation=case.prepared, evidence=sealed)], model)
    )
    assert materialized == eager
    documents = [
        cast("Mapping[str, object]", bind.value)
        for _sql, binds in eager
        for bind in binds
        if isinstance(bind, JsonDocument)
    ]
    assert [document["title"] for document in documents] == [
        "title-1",
        acquisition_support.ASSIGNED_TITLE,
        "title-1",
    ]
    assert all(document["charterCode"] == "NB-118" for document in documents)
    assert documents[0] is stored
    assert documents[2] is stored


def test_a_surviving_row_overlays_an_effective_value_object_and_carries_a_restored_leaf() -> None:
    branch = corpus_model("branch")
    stored_name = "".join(("Central", " Branch"))
    address = {
        "street": "10 Old Road",
        "city": "Helsinki",
        "geo": {"country": "FI"},
        "phones": [{"type": "mobile", "number": "111"}],
    }
    group = temporal_group(
        PredicateWrite(
            "update",
            PredicateSelection("Branch", predicate_algebra.Comparison("eq", "Branch.id", 1)),
            (
                WriteAssignment("Branch.name", "Central Branch"),
                WriteAssignment("Branch.address", {**address, "city": "Tampere"}),
            ),
            _WINDOW_FROM,
        ),
        branch,
        [
            {
                "id": 1,
                "name": stored_name,
                "validStart": _OPENED_AT,
                "validEnd": INFINITY,
                "txStart": _OPENED_AT,
                "txEnd": INFINITY,
                "address": address,
            }
        ],
    )
    assert len(group) == 1
    (changed,) = (
        entry
        for step in _plan([group], branch).steps
        if isinstance(step, PlannedInsert)
        for entry in step.entries
        if isinstance(entry.origin, ChangedFrom)
    )
    name = next(ident for ident in changed.row.attributes if ident.name == "name")
    (address_identity,) = changed.row.value_objects
    assert changed.row.attributes[name] is stored_name
    assert changed.row.value_objects[address_identity] is next(
        assignment.value
        for assignment in group.mutation.managed_assignments
        if not isinstance(assignment.member, AttributeMetadata)
    )
