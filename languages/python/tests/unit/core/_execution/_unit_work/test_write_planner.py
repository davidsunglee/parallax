"""``WritePlanner.finalize`` — the primary neutral seam (m-unit-work, Docker-free).

``WritePlanner.finalize(WritePlanningRequest) -> WritePlan`` is the entire
caller-visible planning surface: no caller sequences coalescing, batching,
ordering, temporal expansion, observation validation, instant acquisition, or
provenance decoration by hand. A caller does resolve the observation a write
settles against, at the verb that holds the value, and buffers it on the write.
These tests drive it directly — through the
SAME production wiring ``parallax.core._execution._planning.build_write_planner``
builds — asserting complete ``PlannedStep`` shapes and plan-wide ordering,
never a private stage function: same-transaction coalescing (insert-then-update
in place per temporal flavor; insert-then-delete cancellation), dependency
ordering over the descriptor graph, empty-change-set elision, batching
(`m-batch-write`),
optimistic-mode gates, and temporal in-place adjacency.
"""

from __future__ import annotations

import dataclasses
import datetime as dt
from collections.abc import Mapping, Sequence
from decimal import Decimal
from typing import cast

import pytest

from parallax.core import predicate as predicate_algebra
from parallax.core import relationship, temporal_read
from parallax.core._execution import _planning as planning_composition
from parallax.core._execution._planning import build_write_planner
from parallax.core._execution._unit_work import keys as keys_module
from parallax.core._execution._unit_work.instructions import (
    PreparedKeyedInstruction,
    PreparedPredicateInstruction,
    derive_keyed_instruction,
    prepare_typed_write,
)
from parallax.core._execution._unit_work.retain import ParticipationToken, ReadEvidence
from parallax.core._execution._unit_work.write_items import (
    ObjectLockedWrite,
    OrderedWrite,
    StateObservedWrite,
)
from parallax.core._execution._unit_work.write_settlement import SettledWriteWithSource
from parallax.core._formation_profile import form_metamodel
from parallax.core.base import INFINITY
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
    UnresolvedDefiningRelationshipDeclaration,
    UnresolvedRelationshipJoin,
)
from parallax.core.relationship import _compile as relationship_compile
from parallax.core.unit_work import (
    AdmittedWrite,
    Concurrency,
    KeyedWriteInstruction,
    PredicateSelection,
    PredicateWriteInstruction,
    RetainedObservation,
    TransactionInstant,
    WriteAssignment,
    WritePlanningRequest,
    object_key,
)
from parallax.core.write_plan import (
    ObjectKey,
    PlannedClose,
    PlannedInsert,
    PredecessorRow,
    StateObservation,
    TemporalObservation,
    VersionObservation,
    WritePlan,
    WritePlanningError,
)
from parallax.core.write_plan.keys import VersionedObjectStateKey
from parallax.core.write_plan.steps import (
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
    PlannedStep,
    PlannedUpdate,
    ResolvedMutationSelection,
    Versioned,
    VersionGate,
)
from parallax.descriptor._records import Metamodel as DescriptorMetamodel
from tests._support.clock_probes import CountingClock, inert_instant, instant_at
from tests._support.planner_probes import (
    TEST_ACTOR_IDENTITY,
    object_source,
    observed_buffer,
    plan_steps,
    retained_observation,
    settled_writes,
)
from tests.unit._corpus_identity_support import corpus_entity, corpus_object_key
from tests.unit._corpus_model_support import corpus_records, formed
from tests.unit._corpus_model_support import model as corpus_model
from tests.unit._metamodel_support import Declaration, attribute, identity, key, source
from tests.unit.core._execution._unit_work._audit_support import RecordingAudit

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


type _TestAdmittedWrite = AdmittedWrite | KeyedWriteInstruction


def _plan(
    buffer: Sequence[_TestAdmittedWrite],
    model: Metamodel,
    *,
    observations: dict[ObjectKey, StateObservation] | None = None,
    concurrency: Concurrency = "locking",
    tx_instant: TransactionInstant | None = None,
) -> WritePlan:
    return build_write_planner(model).finalize(
        WritePlanningRequest(
            actor_identity=TEST_ACTOR_IDENTITY,
            transaction_instant=tx_instant if tx_instant is not None else _INSTANT,
            concurrency=concurrency,
            composed_writes=observed_buffer(buffer, model, observations),
        )
    )


def _row_values(row: PlannedRow) -> dict[str, object]:
    values: dict[str, object] = {ident.name: value for ident, value in row.attributes.items()}
    for ident, value in row.value_objects.items():
        values[ident.path[-1]] = value
    return values


def _insert_rows(step: PlannedStep) -> list[dict[str, object]]:
    assert isinstance(step, PlannedInsert)
    return [_row_values(entry.row) for entry in step.entries]


def _step_entity(step: PlannedStep) -> str:
    return step.entity.name


def _step_mutation(step: PlannedStep) -> str:
    if isinstance(step, PlannedInsert):
        return "insert"
    if isinstance(step, PlannedUpdate):
        return "update"
    if isinstance(step, PlannedClose):
        return "close"
    return "delete"


def _entities(plan: WritePlan) -> list[str]:
    return [_step_entity(step) for step in plan_steps(plan)]


def _key_values(step: PlannedUpdate | PlannedDelete) -> tuple[tuple[object, ...], ...]:
    assert isinstance(step.target, KeyTarget)
    return step.target.key_values


def _single_key(step: PlannedUpdate | PlannedDelete) -> object:
    (values,) = _key_values(step)
    (value,) = values
    return value


def _prepared_keyed(write: KeyedWriteInstruction, model: Metamodel) -> PreparedKeyedInstruction:
    prepared = prepare_typed_write(write, model)
    assert isinstance(prepared, PreparedKeyedInstruction)
    return prepared


def _observed(
    write: KeyedWriteInstruction, evidence: StateObservation | RetainedObservation
) -> StateObservedWrite:
    prepared = _prepared_keyed(write, _ACCOUNT)
    if not isinstance(evidence, RetainedObservation):
        evidence = retained_observation(prepared, _ACCOUNT, evidence)
    return StateObservedWrite(prepared, evidence)


def _claimed(write: KeyedWriteInstruction) -> ObjectLockedWrite:
    (row,) = write.rows
    source = object_source(corpus_object_key("Wallet", ("id", row["id"])))
    return ObjectLockedWrite(_prepared_keyed(write, _WALLET), (source,))


def _shape(plan: WritePlan) -> list[tuple[str, str]]:
    return [(_step_mutation(step), _step_entity(step)) for step in plan_steps(plan)]


# --------------------------------------------------------------------------- #
# Coalesce (m-unit-work "Same-transaction write coalescing").                 #
# --------------------------------------------------------------------------- #
def test_nontemporal_insert_then_update_coalesces_to_one_insert() -> None:
    insert = KeyedWriteInstruction(
        "insert", "Account", ({"id": 9, "owner": "Noether", "balance": Decimal("5.00")},)
    )
    update = KeyedWriteInstruction("amend", "Account", ({"id": 9, "balance": Decimal("99.00")},))
    plan = _plan([insert, update], _ACCOUNT)
    (step,) = plan_steps(plan)
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
    first = KeyedWriteInstruction(
        "amend", "Account", ({"id": 1, "owner": "Grace", "balance": Decimal("125.00")},)
    )
    second = KeyedWriteInstruction("amend", "Account", ({"id": 1, "balance": Decimal("175.00")},))
    plan = _plan([first, second], _ACCOUNT, observations={key: observation})
    (step,) = plan_steps(plan)
    assert isinstance(step, PlannedUpdate)
    assert _assignment_values(step) == {
        "owner": "Grace",
        "balance": Decimal("175.00"),
        "version": 5,
    }


def test_a_restated_member_is_written_as_the_last_word_on_it() -> None:
    # Assignments are literal: a later write setting a member back to the value
    # its source observed is the last word on that member and is written, beside
    # the member only the first write named.
    key = corpus_object_key("Account", ("id", 1))
    observation = VersionObservation(observed_version=4)
    first = KeyedWriteInstruction(
        "amend", "Account", ({"id": 1, "owner": "Grace", "balance": Decimal("125.00")},)
    )
    second = KeyedWriteInstruction("amend", "Account", ({"id": 1, "balance": Decimal("250.00")},))
    plan = _plan([first, second], _ACCOUNT, observations={key: observation})
    (step,) = plan_steps(plan)
    assert isinstance(step, PlannedUpdate)
    assert _assignment_values(step) == {
        "owner": "Grace",
        "balance": Decimal("250.00"),
        "version": 5,
    }


_BALANCE_PREDECESSOR: dict[str, object] = {
    "id": 1,
    "acctNum": "A",
    "value": Decimal("1.00"),
    "txStart": dt.datetime(2024, 1, 1, tzinfo=dt.UTC),
    "txEnd": INFINITY,
}


def _changed_entry(plan: WritePlan) -> tuple[ChangedFrom, PlannedRow]:
    (entry,) = (
        entry
        for step in plan_steps(plan)
        if isinstance(step, PlannedInsert)
        for entry in step.entries
        if isinstance(entry.origin, ChangedFrom)
    )
    return cast("ChangedFrom", entry.origin), entry.row


def test_composed_temporal_writes_overlay_every_member_any_of_them_assigned() -> None:
    # The successor overlays each member at its last assigned value, a value
    # equal to the predecessor's own included, and carries only the members no
    # write named.
    observation = TemporalObservation(predecessor=PredecessorRow(members=_BALANCE_PREDECESSOR))
    plan = _plan(
        [
            KeyedWriteInstruction("amend", "Balance", ({"id": 1, "value": Decimal("9.00")},)),
            KeyedWriteInstruction("amend", "Balance", ({"id": 1, "acctNum": "B"},)),
            KeyedWriteInstruction("amend", "Balance", ({"id": 1, "value": Decimal("1.00")},)),
        ],
        _BALANCE,
        observations={corpus_object_key("Balance", ("id", 1)): observation},
    )
    _origin, row = _changed_entry(plan)
    values = _row_values(row)
    assert values["acctNum"] == "B"
    assert values["value"] == Decimal("1.00")
    (entry,) = (
        entry
        for step in plan_steps(plan)
        if isinstance(step, PlannedInsert)
        for entry in step.entries
        if isinstance(entry.origin, ChangedFrom)
    )
    assert {cast("AttributeIdentity", member).name for member in entry.executed} == {
        "acctNum",
        "value",
    }


def test_a_destructive_intent_supersedes_the_assignments_buffered_before_it() -> None:
    key = corpus_object_key("Account", ("id", 1))
    observation = VersionObservation(observed_version=4)
    update = KeyedWriteInstruction("amend", "Account", ({"id": 1, "balance": Decimal("125.00")},))
    delete = KeyedWriteInstruction("delete", "Account", ({"id": 1},))
    plan = _plan([update, delete], _ACCOUNT, observations={key: observation})
    (step,) = plan_steps(plan)
    assert isinstance(step, PlannedDelete)


def test_identical_destructive_intents_of_one_state_plan_one_step() -> None:
    key = corpus_object_key("Account", ("id", 1))
    observation = VersionObservation(observed_version=4)
    delete = KeyedWriteInstruction("delete", "Account", ({"id": 1},))
    plan = _plan([delete, delete], _ACCOUNT, observations={key: observation})
    (step,) = plan_steps(plan)
    assert isinstance(step, PlannedDelete)


def test_writes_of_two_observed_states_of_one_object_stay_independent() -> None:
    # Coalescing is keyed by the observed STATE, not by the object: two writes
    # settling against two generations of one row are two intents, and merging
    # them would gate the survivor on a version one of them never saw.
    first = _observed(
        KeyedWriteInstruction("amend", "Account", ({"id": 1, "balance": Decimal("125.00")},)),
        VersionObservation(observed_version=4),
    )
    second = _observed(
        KeyedWriteInstruction("amend", "Account", ({"id": 1, "balance": Decimal("175.00")},)),
        VersionObservation(observed_version=5),
    )
    plan = _plan([first, second], _ACCOUNT, concurrency="optimistic")
    assert len(plan_steps(plan)) == 2


def test_a_second_state_of_one_object_does_not_close_the_first_states_claim() -> None:
    # An object's claims are open per observed STATE, so a write of one state
    # standing between two writes of another leaves their claim exactly where it
    # was: the verb admitted the third write as a merge into the first, and
    # emitting it separately would gate two statements on one generation — the
    # second of which no read ever saw current.
    earlier = VersionObservation(observed_version=4)
    later = VersionObservation(observed_version=5)
    first = _observed(
        KeyedWriteInstruction("amend", "Account", ({"id": 1, "balance": Decimal("125.00")},)),
        earlier,
    )
    interleaved = _observed(
        KeyedWriteInstruction("amend", "Account", ({"id": 1, "owner": "Grace"},)), later
    )
    third = _observed(
        KeyedWriteInstruction("amend", "Account", ({"id": 1, "balance": Decimal("175.00")},)),
        earlier,
    )
    plan = _plan([first, interleaved, third], _ACCOUNT, concurrency="optimistic")
    merged, standing = plan_steps(plan)
    assert isinstance(merged, PlannedUpdate)
    assert isinstance(standing, PlannedUpdate)
    assert _assignment_values(merged) == {"balance": Decimal("175.00"), "version": 5}
    assert _assignment_values(standing) == {"owner": "Grace", "version": 6}


def test_object_locked_writes_of_one_unversioned_row_merge_into_one_step() -> None:
    # The object-locked arm reaches the same algebra by the same call: what such
    # writes share is the object, because no state stands behind them.
    first = _claimed(
        KeyedWriteInstruction("amend", "Wallet", ({"id": 1, "balance": Decimal("5.00")},))
    )
    second = _claimed(KeyedWriteInstruction("amend", "Wallet", ({"id": 1, "owner": "Grace"},)))
    plan = _plan([first, second], _WALLET)
    (step,) = plan_steps(plan)
    assert isinstance(step, PlannedUpdate)
    assert _assignment_values(step) == {"balance": Decimal("5.00"), "owner": "Grace"}


def test_an_object_locked_destruction_supersedes_the_assignment_before_it() -> None:
    update = _claimed(
        KeyedWriteInstruction("amend", "Wallet", ({"id": 1, "balance": Decimal("5.00")},))
    )
    delete = _claimed(KeyedWriteInstruction("delete", "Wallet", ({"id": 1},)))
    plan = _plan([update, delete], _WALLET)
    (step,) = plan_steps(plan)
    assert isinstance(step, PlannedDelete)


def test_identical_object_locked_destructions_plan_one_step() -> None:
    # Unclaimed, the pair reaches the batch collapse as a repeated authored key,
    # which a Key Target refuses — so deduplication is what keeps a legal two-verb
    # sequence out of an internal invariant failure.
    delete = _claimed(KeyedWriteInstruction("delete", "Wallet", ({"id": 1},)))
    plan = _plan([delete, delete], _WALLET)
    (step,) = plan_steps(plan)
    assert isinstance(step, PlannedDelete)


def test_object_locked_writes_of_two_rows_still_collapse_into_one_batch() -> None:
    # A claim is per object, so two objects' deletes are two claims — and each
    # batches as the bare instruction it carries would, which is what keeps
    # `m-batch-write`'s set-based collapse reachable for unversioned rows. The
    # batch keeps both sources and destroys both objects.
    first = _claimed(KeyedWriteInstruction("delete", "Wallet", ({"id": 1},)))
    second = _claimed(KeyedWriteInstruction("delete", "Wallet", ({"id": 2},)))
    plan = _plan([first, second], _WALLET)
    (step,) = plan_steps(plan)
    assert isinstance(step, PlannedDelete)
    assert isinstance(step.target, KeyTarget)
    assert step.target.key_values == ((1,), (2,))
    (write,) = settled_writes(plan)
    assert isinstance(write, SettledWriteWithSource)
    assert write.source_evidence == (*first.source_evidence, *second.source_evidence)
    keys = tuple(corpus_object_key("Wallet", ("id", key)) for key in (1, 2))
    assert (tuple(write.changed), write.destroyed, write.advanced) == (keys, keys, ())


def _assignment_values(step: PlannedUpdate) -> dict[str, object]:
    return {ident.name: value for ident, value in step.assignments.attributes.items()}


def test_audit_insert_then_update_coalesces_in_place() -> None:
    insert = KeyedWriteInstruction(
        "insert", "Balance", ({"id": 9, "acctNum": "D", "value": Decimal("100.00")},)
    )
    update = KeyedWriteInstruction("amend", "Balance", ({"id": 9, "value": Decimal("150.00")},))
    plan = _plan([insert, update], _BALANCE, tx_instant=instant_at(_B1))
    (step,) = plan_steps(plan)
    assert isinstance(step, PlannedInsert)  # one current milestone, no close
    (row,) = _insert_rows(step)
    assert row["acctNum"] == "D"
    assert row["value"] == Decimal("150.00")
    assert row["txStart"] == _B1_MANAGED


def test_bitemporal_insert_then_update_keeps_the_valid_time_bound() -> None:
    insert = KeyedWriteInstruction(
        "insert",
        "Position",
        ({"id": 9, "acctNum": "D", "value": Decimal("100.00")},),
        valid_from=_B1_MANAGED,
    )
    update = KeyedWriteInstruction(
        "amend", "Position", ({"id": 9, "value": Decimal("150.00")},), valid_from=_B1_MANAGED
    )
    plan = _plan([insert, update], _POSITION, tx_instant=instant_at(_B1))
    (step,) = plan_steps(plan)
    assert isinstance(step, PlannedInsert)  # one fully-current rectangle, no head/tail split
    (row,) = _insert_rows(step)
    assert row["acctNum"] == "D"
    assert row["value"] == Decimal("150.00")
    assert row["validStart"] == _B1_MANAGED


def test_insert_then_delete_cancels_to_no_dml() -> None:
    insert = KeyedWriteInstruction(
        "insert", "Account", ({"id": 9, "owner": "Noether", "balance": Decimal("5.00")},)
    )
    delete = KeyedWriteInstruction("delete", "Account", ({"id": 9},))
    plan = _plan([insert, delete], _ACCOUNT)
    assert len(plan_steps(plan)) == 0  # both annihilate — the net-zero elision across two verbs


def test_insert_then_multiple_updates_fold_into_one_insert() -> None:
    insert = KeyedWriteInstruction(
        "insert", "Account", ({"id": 9, "owner": "Noether", "balance": Decimal("5.00")},)
    )
    update1 = KeyedWriteInstruction("amend", "Account", ({"id": 9, "balance": Decimal("50.00")},))
    update2 = KeyedWriteInstruction("amend", "Account", ({"id": 9, "owner": "Markov"},))
    plan = _plan([insert, update1, update2], _ACCOUNT)
    (step,) = plan_steps(plan)
    (row,) = _insert_rows(step)
    assert row["owner"] == "Markov"
    assert row["balance"] == Decimal("50.00")


def test_update_of_a_row_not_inserted_this_transaction_is_not_coalesced() -> None:
    update = KeyedWriteInstruction("amend", "Wallet", ({"id": 1, "balance": Decimal("0.00")},))
    plan = _plan([update], _WALLET)
    (step,) = plan_steps(plan)
    assert isinstance(step, PlannedUpdate)


def test_delete_of_a_row_not_inserted_this_transaction_is_not_coalesced() -> None:
    delete = KeyedWriteInstruction("delete", "Wallet", ({"id": 1},))
    plan = _plan([delete], _WALLET)
    (step,) = plan_steps(plan)
    assert isinstance(step, PlannedDelete)


# --------------------------------------------------------------------------- #
# Dependency ordering (foreign-key parents-before-children).                  #
# --------------------------------------------------------------------------- #
def test_inserts_order_parents_before_children() -> None:
    buffer: list[_TestAdmittedWrite] = [
        KeyedWriteInstruction("insert", "OrderStatus", ({"id": 100, "orderId": 1, "code": "new"},)),
        KeyedWriteInstruction(
            "insert", "OrderTag", ({"id": 1000, "orderId": 1, "label": "x", "priority": 1},)
        ),
        KeyedWriteInstruction(
            "insert", "OrderItem", ({"id": 10, "orderId": 1, "sku": "A", "quantity": 1},)
        ),
        KeyedWriteInstruction(
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
    buffer: list[_TestAdmittedWrite] = [
        KeyedWriteInstruction("delete", "Order", ({"id": 1},)),
        KeyedWriteInstruction("delete", "OrderItem", ({"id": 10},)),
        KeyedWriteInstruction("delete", "OrderStatus", ({"id": 100},)),
    ]
    plan = _plan(buffer, _ORDERS)
    assert _entities(plan) == ["OrderStatus", "OrderItem", "Order"]


def test_mixed_flush_is_insert_then_update_then_delete() -> None:
    buffer: list[_TestAdmittedWrite] = [
        KeyedWriteInstruction("delete", "OrderStatus", ({"id": 100},)),
        KeyedWriteInstruction("amend", "OrderItem", ({"id": 10, "quantity": 5},)),
        KeyedWriteInstruction(
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
    buffer: list[_TestAdmittedWrite] = [
        KeyedWriteInstruction("insert", "Person", ({"id": 1, "name": "A"},)),
        KeyedWriteInstruction("insert", "Passport", ({"id": 2, "personId": 1, "number": "X"},)),
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
    buffer: list[_TestAdmittedWrite] = [
        KeyedWriteInstruction("insert", "Alpha", ({"id": 1, "zetaId": 2},)),
        KeyedWriteInstruction("insert", "Zeta", ({"id": 2},)),
    ]
    assert _entities(_plan(buffer, model)) == ["Zeta", "Alpha"]


def test_ordering_reads_each_ranked_writes_compiled_rank_once_and_derives_none(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Ranks are the Relationship Facet's, compiled with the model: a flush only
    # reads one per insert or delete. Updates keep authored order, so they never
    # ask.
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
    buffer: list[_TestAdmittedWrite] = [
        KeyedWriteInstruction(
            "insert", "OrderItem", ({"id": 10, "orderId": 1, "sku": "A", "quantity": 1},)
        ),
        KeyedWriteInstruction("amend", "OrderItem", ({"id": 11, "quantity": 5},)),
        KeyedWriteInstruction("delete", "OrderStatus", ({"id": 100},)),
        KeyedWriteInstruction(
            "insert", "OrderTag", ({"id": 7, "orderId": 1, "label": "x", "priority": 1},)
        ),
    ]
    request = WritePlanningRequest(
        actor_identity=TEST_ACTOR_IDENTITY,
        transaction_instant=_INSTANT,
        concurrency="locking",
        composed_writes=observed_buffer(buffer, _ORDERS, None),
    )
    first = planner.finalize(request)
    second = planner.finalize(request)
    assert asked == ["OrderItem", "OrderStatus", "OrderTag"] * 2
    assert (
        _shape(first)
        == _shape(second)
        == [
            ("insert", "OrderItem"),
            ("insert", "OrderTag"),
            ("update", "OrderItem"),
            ("delete", "OrderStatus"),
        ]
    )


def test_an_instruction_naming_an_undeclared_entity_is_a_planning_error() -> None:
    # Every settled step needs its Entity resolved (`_require_entity`), so an
    # instruction naming one the accepted Metamodel does not declare is refused
    # as a caller wiring defect during planning — never silently ranked first
    # by the ordering stage's own defensive fallback and lowered anyway.
    buffer: list[_TestAdmittedWrite] = [
        KeyedWriteInstruction(
            "insert", "OrderItem", ({"id": 10, "orderId": 1, "sku": "A", "quantity": 1},)
        ),
        KeyedWriteInstruction("insert", "Gadget", ({"id": 1, "name": "G"},)),
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
    buffer: list[_TestAdmittedWrite] = [KeyedWriteInstruction("amend", "Gadget", ({"id": 1},))]
    with pytest.raises(ValueError, match="Gadget"):
        _plan(buffer, _ORDERS)


# --------------------------------------------------------------------------- #
# A predicate-selected write is planned alone, as its one readless statement.  #
# --------------------------------------------------------------------------- #
def _predicate_step(
    instruction: PredicateWriteInstruction, model: Metamodel
) -> PlannedUpdate | PlannedDelete:
    prepared = prepare_typed_write(instruction, model)
    assert isinstance(prepared, PreparedPredicateInstruction)
    return build_write_planner(model).predicate_step(
        prepared, actor_identity=TEST_ACTOR_IDENTITY, transaction_instant=_INSTANT
    )


def test_a_predicate_update_is_one_unversioned_statement_over_its_selection() -> None:
    step = _predicate_step(
        PredicateWriteInstruction(
            "amend",
            PredicateSelection(
                "Order",
                predicate_algebra.Comparison("eq", predicate_algebra.FieldSubject("Order.id"), 1),
            ),
            assignments=(WriteAssignment("Order.name", "Z"),),
        ),
        _ORDERS,
    )
    assert isinstance(step, PlannedUpdate)
    assert step.concurrency == UNVERSIONED
    assert step.affected_rows == ANY_COUNT
    assert isinstance(step.target, ResolvedMutationSelection)
    assert step.target.predicate == predicate_algebra.validate_predicate(
        step.target.target,
        predicate_algebra.Comparison("eq", predicate_algebra.FieldSubject("Order.id"), 1),
        _ORDERS,
    )


# --------------------------------------------------------------------------- #
# Elision (m-unit-work "eliminate known cancellation and no-op work").        #
# --------------------------------------------------------------------------- #
def test_empty_change_set_update_emits_no_instruction() -> None:
    update = KeyedWriteInstruction("amend", "Wallet", ({"id": 1},))  # only the PK: no changed field
    plan = _plan([update], _WALLET)
    assert len(plan_steps(plan)) == 0


def test_nonempty_change_set_update_survives_elision() -> None:
    update = KeyedWriteInstruction("amend", "Wallet", ({"id": 1, "balance": Decimal("7.00")},))
    plan = _plan([update], _WALLET)
    assert len(plan_steps(plan)) == 1


def test_a_key_only_row_of_a_preformed_multi_row_update_is_eliminated() -> None:
    # Stage 2 eliminates known no-op work per ROW, not only per instruction: a
    # preformed update mixing a key-only row with an assigning one is not empty
    # as a whole, so an instruction-level test would pass it to batching, which
    # splits it into its rows and hands the key-only child an update with no
    # member to write. Eliminating the row here also keeps the elimination
    # ahead of batching, where the normative stage order puts it.
    update = KeyedWriteInstruction(
        "amend", "Wallet", ({"id": 1}, {"id": 2, "balance": Decimal("9.00")})
    )
    plan = _plan([update], _WALLET)
    (step,) = plan_steps(plan)
    assert isinstance(step, PlannedUpdate)
    assert _key_values(step) == ((2,),)


def test_a_preformed_update_whose_rows_are_all_key_only_is_eliminated_whole() -> None:
    update = KeyedWriteInstruction("amend", "Wallet", ({"id": 1}, {"id": 2}))
    assert len(plan_steps(_plan([update], _WALLET))) == 0


def test_a_plural_temporal_update_is_refused_rather_than_narrowed_by_no_op_elimination() -> None:
    # Row-level elimination never rescues a plural temporal instruction into a
    # legal singleton: dropping the key-only row would silently discard one of
    # the two milestone chains the author wrote, which is exactly the reduction
    # `m-unit-work` requires an implementation to refuse.
    update = KeyedWriteInstruction(
        "amend", "Balance", ({"id": 1}, {"id": 2, "value": Decimal("9.00")})
    )
    with pytest.raises(ValueError, match="temporal target carries 2 rows"):
        _plan([update], _BALANCE)


def test_a_plural_temporal_update_of_key_only_rows_is_refused_rather_than_eliminated() -> None:
    # The same contract when elimination would take the WHOLE instruction: a
    # plural temporal update every row of which is key-only must still be
    # refused, because `m-unit-work`'s singleton rule admits no exception and an
    # empty plan would report that two authored milestone chains were fine. The
    # mixed-row shape above cannot pin this: there, a surviving row keeps the
    # instruction alive on its way to the refusal.
    update = KeyedWriteInstruction("amend", "Balance", ({"id": 1}, {"id": 2}))
    with pytest.raises(ValueError, match="temporal target carries 2 rows"):
        _plan([update], _BALANCE)


def test_a_single_row_temporal_update_naming_only_its_key_is_still_eliminated() -> None:
    # Elimination is unchanged for the row count the singleton rule admits: one
    # temporal row assigning nothing opens no successor worth chaining, so
    # stage 2 removes it exactly as it removes a non-temporal one.
    update = KeyedWriteInstruction("amend", "Balance", ({"id": 1},))
    assert len(plan_steps(_plan([update], _BALANCE))) == 0


def test_empty_plan_from_empty_buffer() -> None:
    plan = _plan([], _ACCOUNT)
    assert plan == WritePlan()
    assert len(plan_steps(plan)) == 0


# --------------------------------------------------------------------------- #
# Object identity (unaffected by the planner surface — a standalone helper).  #
# --------------------------------------------------------------------------- #
def test_object_key_of_a_single_row_keyed_write() -> None:
    key_ = object_key(
        KeyedWriteInstruction("amend", "Account", ({"id": 1, "balance": 0},)), _ACCOUNT
    )
    assert key_ == corpus_object_key("Account", ("id", 1))


def test_object_key_is_none_for_unidentifiable_writes() -> None:
    assert (
        object_key(KeyedWriteInstruction("insert", "Account", ({"id": 1}, {"id": 2})), _ACCOUNT)
        is None
    )
    assert (
        object_key(KeyedWriteInstruction("insert", "Account", ({"owner": "Ada"},)), _ACCOUNT)
        is None
    )
    predicate = PredicateWriteInstruction(
        "delete", PredicateSelection("Account", predicate_algebra.TrueNode())
    )
    assert object_key(predicate, _ACCOUNT) is None


def test_object_key_is_none_for_an_entity_the_model_does_not_declare() -> None:
    assert object_key(KeyedWriteInstruction("delete", "Blob", ({"data": "x"},)), _ACCOUNT) is None


def test_object_key_names_the_resolved_identity_not_the_instructions_spelling() -> None:
    # A write instruction is a serialized document, so it carries whichever
    # spelling its author wrote. Both name one Entity, so both must reach the
    # one key an observation was recorded under — the key names the RESOLVED
    # Entity Identity rather than the spelling that reached it.
    row = ({"id": 1, "balance": 0},)
    bare = object_key(KeyedWriteInstruction("amend", "Account", row), _ACCOUNT)
    canonical = object_key(
        KeyedWriteInstruction("amend", "parallax.compatibility.Account", row), _ACCOUNT
    )
    assert bare == canonical == corpus_object_key("Account", ("id", 1))


def test_object_key_resolves_the_family_effective_primary_key() -> None:
    # `CardPayment`'s own compiled record carries no `id` attribute at all (it
    # is declared on the family root `Payment` alone, m-inheritance "Inherited
    # members") -- a bare `Entity.primary_key` view would wrongly see no key,
    # making every inheritance-family keyed write unidentifiable.
    key_ = object_key(
        KeyedWriteInstruction("amend", "CardPayment", ({"id": 1, "amount": Decimal("5.00")},)),
        _PAYMENT,
    )
    assert key_ == corpus_object_key("CardPayment", ("id", 1))


def test_object_key_is_none_for_a_marker_shaped_primary_key_value() -> None:
    # A pk-gen `max` insert's row carries a DB-computed marker for the id, not
    # a real value (`{computed: "maxPlusOne"}`, `m-pk-gen`): it has no
    # coalescing identity, exactly like an absent pk.
    marker_insert = KeyedWriteInstruction(
        "insert", "Attendee", ({"id": {"computed": "maxPlusOne"}, "name": "Ada"},)
    )
    assert object_key(marker_insert, _PK_MAX) is None
    # And it must not crash any planning stage that keys off it.
    plan = _plan([marker_insert], _PK_MAX)
    (step,) = plan_steps(plan)
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
    card = KeyedWriteInstruction("amend", "CardPayment", ({"id": 1, "amount": Decimal("5.00")},))
    account = KeyedWriteInstruction("amend", "Account", ({"id": 2, "balance": Decimal("0.00")},))
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
    row1 = KeyedWriteInstruction("amend", "Account", ({"id": 1, "balance": Decimal("0.00")},))
    row2 = KeyedWriteInstruction("amend", "Account", ({"id": 2, "balance": Decimal("0.00")},))
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
    for step in plan_steps(plan):
        assert isinstance(step, PlannedUpdate)
        row_id = _single_key(step)
        advanced[row_id] = _row_values_from_assignments(step)["version"]
    assert advanced == {1: 4, 2: 11}  # each advances from its OWN recorded observation


def test_an_observation_on_an_unversioned_non_temporal_update_is_refused() -> None:
    # `m-unit-work`: "unversioned Non-Temporal writes have no observation", and
    # that absence is structural. The observed write can only refuse the half it can
    # see without the model (an insert, a plural instruction); the planner is
    # the model-aware boundary every admitted write crosses, so it refuses the other
    # half rather than settling the write with the evidence discarded.
    update = KeyedWriteInstruction("amend", "Wallet", ({"id": 1, "balance": Decimal("7.00")},))
    key_ = object_key(update, _WALLET)
    assert key_ is not None
    with pytest.raises(WritePlanningError, match="unversioned Non-Temporal 'amend'"):
        _plan([update], _WALLET, observations={key_: VersionObservation(observed_version=3)})


def test_an_observation_on_an_unversioned_non_temporal_delete_is_refused() -> None:
    delete = KeyedWriteInstruction("delete", "Wallet", ({"id": 1},))
    key_ = object_key(delete, _WALLET)
    assert key_ is not None
    with pytest.raises(WritePlanningError, match="unversioned Non-Temporal 'delete'"):
        _plan([delete], _WALLET, observations={key_: VersionObservation(observed_version=3)})


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
    update = KeyedWriteInstruction("amend", "Account", ({"id": 1, "balance": Decimal("175.00")},))
    key_ = object_key(update, _ACCOUNT)
    assert key_ is not None
    plan = _plan(
        [update],
        _ACCOUNT,
        observations={key_: VersionObservation(observed_version=3)},
        concurrency="optimistic",
    )
    (step,) = plan_steps(plan)
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
    delete = KeyedWriteInstruction("delete", "Wallet", ({"id": 1},))
    plan = _plan([delete], _WALLET, concurrency="optimistic")
    (step,) = plan_steps(plan)
    assert isinstance(step, PlannedDelete)
    assert step.concurrency == UNVERSIONED
    (under_locking,) = plan_steps(_plan([delete], _WALLET))
    assert isinstance(under_locking, PlannedDelete)
    assert under_locking.concurrency == step.concurrency


def test_a_versioned_delete_with_a_recorded_observation_is_ungated_under_locking() -> None:
    delete = KeyedWriteInstruction("delete", "Account", ({"id": 1},))
    key_ = object_key(delete, _ACCOUNT)
    assert key_ is not None
    plan = _plan([delete], _ACCOUNT, observations={key_: VersionObservation(observed_version=3)})
    (step,) = plan_steps(plan)
    assert isinstance(step, PlannedDelete)
    assert step.concurrency == Versioned(
        attribute=AttributeIdentity(_ACCOUNT.entities[0].identity, "version"), gate=UNGATED
    )
    assert step.affected_rows == ExactCount(1, STALE_WRITE)


def test_an_observation_free_multi_key_delete_carries_the_aggregate_missing_target_policy() -> None:
    delete = KeyedWriteInstruction("delete", "Wallet", ({"id": 1}, {"id": 2}))
    plan = _plan([delete], _WALLET)
    (step,) = plan_steps(plan)
    assert isinstance(step, PlannedDelete)
    assert isinstance(step.target, KeyTarget)
    assert step.target.key_values == ((1,), (2,))
    # One multi-key Key Target owns ONE aggregate expectation (ADR 0044): the
    # target's own key count, classified by the observation-free keyed rule.
    assert step.affected_rows == ExactCount(2, MISSING_TARGET)


def test_an_unversioned_multi_key_update_settles_to_one_aggregate_planned_step() -> None:
    # The delete above proves the aggregate expectation on the destructive verb;
    # this is the assigning one, and together they fix the cardinality an
    # addressed write keeps whichever verb it carries. A collapsed run is ONE
    # statement over one multi-key Key Target, so it settles to one Planned
    # Update whose expectation is the whole target's key count — never one step
    # per key.
    buffer: list[_TestAdmittedWrite] = [
        KeyedWriteInstruction("amend", "Wallet", ({"id": 1, "balance": Decimal("5.00")},)),
        KeyedWriteInstruction("amend", "Wallet", ({"id": 2, "balance": Decimal("5.00")},)),
        KeyedWriteInstruction("amend", "Wallet", ({"id": 3, "balance": Decimal("5.00")},)),
    ]
    plan = _plan(buffer, _WALLET)
    (step,) = plan_steps(plan)
    assert isinstance(step, PlannedUpdate)
    assert _key_values(step) == ((1,), (2,), (3,))
    assert step.concurrency == UNVERSIONED
    assert step.affected_rows == ExactCount(3, MISSING_TARGET)


def test_a_readless_predicate_delete_carries_an_unbounded_expectation() -> None:
    predicate = predicate_algebra.Comparison(
        "lessThan", predicate_algebra.FieldSubject("Wallet.balance"), "200.00"
    )
    step = _predicate_step(
        PredicateWriteInstruction("delete", PredicateSelection("Wallet", predicate)), _WALLET
    )
    assert isinstance(step, PlannedDelete)
    assert step.affected_rows == ANY_COUNT
    assert isinstance(step.target, ResolvedMutationSelection)
    assert step.target.predicate == predicate_algebra.validate_predicate(
        step.target.target, predicate, _WALLET
    )


# --------------------------------------------------------------------------- #
# Batching (m-batch-write's collapse-eligibility policy, production-wired).   #
# --------------------------------------------------------------------------- #
def test_batching_merges_adjacent_same_entity_same_mutation_inserts() -> None:
    buffer: list[_TestAdmittedWrite] = [
        KeyedWriteInstruction(
            "insert", "Wallet", ({"id": 1, "owner": "Ada", "balance": Decimal("1.00")},)
        ),
        KeyedWriteInstruction(
            "insert", "Wallet", ({"id": 2, "owner": "Bo", "balance": Decimal("2.00")},)
        ),
        KeyedWriteInstruction(
            "insert", "Wallet", ({"id": 3, "owner": "Cy", "balance": Decimal("3.00")},)
        ),
    ]
    plan = _plan(buffer, _WALLET)
    (step,) = plan_steps(plan)
    assert isinstance(step, PlannedInsert)
    assert len(step.entries) == 3


def test_batching_merges_uniform_updates_but_not_a_lone_row() -> None:
    buffer: list[_TestAdmittedWrite] = [
        KeyedWriteInstruction("amend", "Wallet", ({"id": 1, "balance": Decimal("5.00")},))
    ]
    plan = _plan(buffer, _WALLET)
    (step,) = plan_steps(plan)
    assert isinstance(step, PlannedUpdate)
    assert len(_key_values(step)) == 1  # a single row is never a "run"


def test_a_known_no_op_between_two_uniform_updates_does_not_prevent_their_batch() -> None:
    # No-op elimination (m-unit-work stage 2) precedes batching (stage 3): a
    # buffered update naming only its own primary key is eliminated before
    # `_form_batches` ever sees the buffer, so it cannot occupy the run
    # boundary between the two uniform updates surrounding it. Batching first
    # would instead leave the no-op splitting the run, and the two survivors
    # would settle as two separate singleton steps rather than one batch.
    buffer: list[_TestAdmittedWrite] = [
        KeyedWriteInstruction("amend", "Wallet", ({"id": 1, "balance": Decimal("5.00")},)),
        KeyedWriteInstruction("amend", "Wallet", ({"id": 2},)),  # a known no-op: only the PK
        KeyedWriteInstruction("amend", "Wallet", ({"id": 3, "balance": Decimal("5.00")},)),
    ]
    plan = _plan(buffer, _WALLET)
    (step,) = plan_steps(plan)
    assert isinstance(step, PlannedUpdate)
    assert _key_values(step) == ((1,), (3,))


def test_batching_declines_a_non_uniform_update_run_leaving_rows_separate() -> None:
    buffer: list[_TestAdmittedWrite] = [
        KeyedWriteInstruction("amend", "Wallet", ({"id": 1, "balance": Decimal("111.00")},)),
        KeyedWriteInstruction("amend", "Wallet", ({"id": 2, "balance": Decimal("222.00")},)),
    ]
    plan = _plan(buffer, _WALLET)
    assert len(plan_steps(plan)) == 2  # `batch_write.update_collapses` declines: not uniform


def test_batching_never_regroups_across_an_intervening_different_entity() -> None:
    buffer: list[_TestAdmittedWrite] = [
        KeyedWriteInstruction(
            "insert", "Wallet", ({"id": 1, "owner": "Ada", "balance": Decimal("1.00")},)
        ),
        KeyedWriteInstruction("insert", "Person", ({"id": 99, "name": "P"},)),
        KeyedWriteInstruction(
            "insert", "Wallet", ({"id": 2, "owner": "Bo", "balance": Decimal("2.00")},)
        ),
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
        for step in plan_steps(plan)
        if isinstance(step, PlannedInsert) and step.entity.name == "Wallet"
    ]
    assert len(wallet_steps) == 2


def test_batching_never_merges_a_row_carrying_a_recorded_observation() -> None:
    # Two adjacent updates of one versioned entity assigning the SAME value are
    # exactly what the collapse decision admits — and they still settle as two
    # steps, because each arrives wrapped in its own observed write and a
    # multi-row instruction has no way to carry a per-row observation forward.
    # Both rows are observed because only an observed write of a versioned row
    # can be planned at all; the exclusion is therefore proven on the shape
    # production actually produces, not on an unversioned stand-in.
    row1 = KeyedWriteInstruction("amend", "Account", ({"id": 1, "balance": Decimal("5.00")},))
    row2 = KeyedWriteInstruction("amend", "Account", ({"id": 2, "balance": Decimal("5.00")},))
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
    assert len(plan_steps(plan)) == 2


# --------------------------------------------------------------------------- #
# Transaction Instant laziness through the full pipeline (ADR 0010).          #
# --------------------------------------------------------------------------- #
def test_planning_never_captures_the_transaction_instant_for_canceled_work() -> None:
    # The stage order's whole point: coalescing cancels the pair before any
    # surviving write could need a Transaction-Time boundary, so the clock
    # behind the holder the request carries is never consulted.
    clock = CountingClock([dt.datetime(2024, 6, 1, tzinfo=dt.UTC)])
    insert = KeyedWriteInstruction(
        "insert", "Account", ({"id": 1, "owner": "Ada", "balance": Decimal("1.00")},)
    )
    delete = KeyedWriteInstruction("delete", "Account", ({"id": 1},))
    plan = _plan([insert, delete], _ACCOUNT, tx_instant=TransactionInstant(clock))
    assert len(plan_steps(plan)) == 0
    assert clock.calls == 0


def test_planning_captures_the_transaction_instant_only_for_surviving_temporal_work() -> None:
    clock = CountingClock([dt.datetime(2024, 6, 1, tzinfo=dt.UTC)])
    non_temporal = KeyedWriteInstruction(
        "insert", "Wallet", ({"id": 1, "owner": "Ada", "balance": Decimal("1.00")},)
    )
    plan = _plan([non_temporal], _WALLET, tx_instant=TransactionInstant(clock))
    assert len(plan_steps(plan)) == 1
    assert clock.calls == 0

    temporal_clock = CountingClock([dt.datetime(2024, 6, 1, tzinfo=dt.UTC)])
    temporal = KeyedWriteInstruction(
        "insert", "Balance", ({"id": 1, "acctNum": "A", "value": Decimal("1.00")},)
    )
    plan = _plan([temporal], _BALANCE, tx_instant=TransactionInstant(temporal_clock))
    (step,) = plan_steps(plan)
    assert isinstance(step, PlannedInsert)
    assert _insert_rows(step)[0]["txStart"] == dt.datetime(2024, 6, 1, tzinfo=dt.UTC)
    assert temporal_clock.calls == 1


# --------------------------------------------------------------------------- #
# Temporal in-place expansion (ADR 0045): a write's close and its successors  #
# stay at the mutation's already-decided position, between the phases around  #
# it, through the SAME ordering + settling pipeline as everything else; only  #
# its own Write Group's other objects come between them (ADR 0076).           #
# --------------------------------------------------------------------------- #
def test_a_bounded_bitemporal_update_expands_in_place_between_unrelated_writes() -> None:
    # Dependency ordering buckets by verb (inserts, then updates, then
    # deletes) within one region, so an unrelated INSERT and an unrelated
    # DELETE naturally flank the temporal UPDATE bucket — exactly the position
    # its close-and-successors run must occupy as one indivisible write.
    position_update = KeyedWriteInstruction(
        "amend",
        "Position",
        ({"id": 5, "value": Decimal("42.0")},),
        valid_from=dt.datetime(2024, 3, 1, tzinfo=dt.UTC),
    )
    key_ = object_key(position_update, _POSITION)
    assert key_ is not None
    buffer: list[_TestAdmittedWrite] = [
        KeyedWriteInstruction(
            "insert", "Wallet", ({"id": 1, "owner": "Ada", "balance": Decimal("1.00")},)
        ),
        position_update,
        KeyedWriteInstruction("delete", "Wallet", ({"id": 2},)),
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
    kinds = [_step_mutation(step) for step in plan_steps(plan)]
    assert kinds[0] == "insert"
    assert kinds[-1] == "delete"
    middle = kinds[1:-1]
    assert middle[0] == "close"
    assert all(k == "insert" for k in middle[1:])
    assert len(middle) >= 2  # a close plus at least one chained successor


def _position_value_and_valid_time(step: PlannedStep) -> list[tuple[object, ...]]:
    return [(row["value"], row["validStart"], row["validEnd"]) for row in _insert_rows(step)]


def _amendments_assigning_one_value_from_march() -> list[KeyedWriteInstruction]:
    return [
        KeyedWriteInstruction(
            "amendUntil",
            "Position",
            ({"id": 5, "value": Decimal("2.0")},),
            valid_from=dt.datetime(2024, 3, 1, tzinfo=dt.UTC),
            until=dt.datetime(2024, 6, 1, tzinfo=dt.UTC),
        ),
        KeyedWriteInstruction(
            "amend",
            "Position",
            ({"id": 5, "value": Decimal("2.0")},),
            valid_from=dt.datetime(2024, 6, 1, tzinfo=dt.UTC),
        ),
    ]


def test_composed_amendments_leaving_one_state_open_one_row_after_their_close() -> None:
    amendments = _amendments_assigning_one_value_from_march()
    key_ = object_key(amendments[0], _POSITION)
    assert key_ is not None
    plan = _plan(
        amendments,
        _POSITION,
        observations={key_: _bitemporal_observation()},
        tx_instant=instant_at("2024-07-01T00:00:00+00:00"),
    )
    close, *inserts = plan_steps(plan)
    assert isinstance(close, PlannedClose)
    assert [_position_value_and_valid_time(step) for step in inserts] == [
        [
            (
                Decimal("1.0"),
                dt.datetime(2024, 1, 1, tzinfo=dt.UTC),
                dt.datetime(2024, 3, 1, tzinfo=dt.UTC),
            )
        ],
        [(Decimal("2.0"), dt.datetime(2024, 3, 1, tzinfo=dt.UTC), INFINITY)],
    ]


def test_a_pending_insertion_amended_into_one_state_opens_one_row_for_it() -> None:
    plan = _plan(
        [
            KeyedWriteInstruction(
                "insert",
                "Position",
                ({"id": 5, "acctNum": "P5", "value": Decimal("1.0")},),
                valid_from=dt.datetime(2024, 1, 1, tzinfo=dt.UTC),
            ),
            *_amendments_assigning_one_value_from_march(),
        ],
        _POSITION,
        tx_instant=instant_at("2024-07-01T00:00:00+00:00"),
    )
    assert [_position_value_and_valid_time(step) for step in plan_steps(plan)] == [
        [
            (
                Decimal("1.0"),
                dt.datetime(2024, 1, 1, tzinfo=dt.UTC),
                dt.datetime(2024, 3, 1, tzinfo=dt.UTC),
            )
        ],
        [(Decimal("2.0"), dt.datetime(2024, 3, 1, tzinfo=dt.UTC), INFINITY)],
    ]


def _bitemporal_observation() -> StateObservation:
    return TemporalObservation(
        predecessor=PredecessorRow(
            members={
                "id": 5,
                "acctNum": "P5",
                "value": Decimal("1.0"),
                "validStart": dt.datetime(2024, 1, 1, tzinfo=dt.UTC),
                "validEnd": INFINITY,
                "txStart": dt.datetime(2024, 1, 1, tzinfo=dt.UTC),
                "txEnd": INFINITY,
            }
        )
    )


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
    # keyed insert, observed versioned update, and a bitemporal mutation — and
    # so is a readless predicate write's own planning, with the scan wired to
    # fail, so reaching it at all is the failure rather than a slow path.
    model = formed(
        DescriptorMetamodel(
            entities=(
                *_MODELS["wallet"].entities,
                *_MODELS["account"].entities,
                *_MODELS["position"].entities,
            )
        )
    )
    account_update = KeyedWriteInstruction(
        "amend", "Account", ({"id": 3, "balance": Decimal("7.00")},)
    )
    position_update = KeyedWriteInstruction(
        "amend",
        "Position",
        ({"id": 5, "value": Decimal("42.0")},),
        valid_from=dt.datetime(2024, 3, 1, tzinfo=dt.UTC),
    )
    account_key = object_key(account_update, model)
    position_key = object_key(position_update, model)
    assert account_key is not None and position_key is not None
    buffer: list[_TestAdmittedWrite] = [
        KeyedWriteInstruction(
            "insert", "Wallet", ({"id": 1, "owner": "Ada", "balance": Decimal("1.00")},)
        ),
        account_update,
        position_update,
    ]
    predicate = prepare_typed_write(
        PredicateWriteInstruction(
            "delete",
            PredicateSelection(
                "Wallet",
                predicate_algebra.Comparison("eq", predicate_algebra.FieldSubject("Wallet.id"), 2),
            ),
        ),
        model,
    )
    assert isinstance(predicate, PreparedPredicateInstruction)
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

    # Key derivation's binding is the one a flush could reach the model's
    # spelling rule through.
    monkeypatch.setattr(keys_module, "entity_by_name", refuse)
    planner = build_write_planner(model)
    plan = planner.finalize(
        WritePlanningRequest(
            actor_identity=TEST_ACTOR_IDENTITY,
            transaction_instant=instant_at("2024-06-01T00:00:00+00:00"),
            concurrency="optimistic",
            composed_writes=prepared,
        )
    )
    kinds = [_step_mutation(step) for step in plan_steps(plan)]
    assert kinds.count("insert") >= 2  # the Wallet insert, plus the bitemporal successors
    assert "close" in kinds
    assert kinds.count("update") == 1  # the addressed Account update
    step = planner.predicate_step(
        predicate,
        actor_identity=TEST_ACTOR_IDENTITY,
        transaction_instant=instant_at("2024-06-01T00:00:00+00:00"),
    )
    assert isinstance(step, PlannedDelete)


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


def _temporal_family_writes() -> list[OrderedWrite]:
    """Observed updates of an inherited Transaction-Time-Only and an inherited
    Bitemporal position."""
    quote = KeyedWriteInstruction("amend", "SpotQuote", ({"id": 1, "price": Decimal("2.00")},))
    rate = KeyedWriteInstruction(
        "amend",
        "DepositRate",
        ({"id": 2, "amount": Decimal("3.00")},),
        valid_from=dt.datetime(2024, 3, 1, tzinfo=dt.UTC),
    )
    transaction_time = {"txStart": _OPENED, "txEnd": INFINITY}
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
            "validEnd": INFINITY,
            **transaction_time,
        },
    }
    return [
        *observed_buffer(
            [quote, rate],
            _TEMPORAL_FAMILIES,
            {
                key_: TemporalObservation(predecessor=PredecessorRow(members=members))
                for key_, members in observed.items()
            },
        ),
    ]


def test_settlement_reads_each_temporal_mutations_family_shape_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # One read per addressed write, and none on step access: the shape dispatch
    # read is the one every later decision — geometry, close address, gate,
    # successor binding — reuses.
    facet = temporal_read.view(_TEMPORAL_FAMILIES)
    buffered = _temporal_family_writes()
    planner = build_write_planner(_TEMPORAL_FAMILIES)
    reads: list[str] = []
    read_shape = type(facet).shape

    def counting(self: temporal_read.TemporalFacet, entity: EntityIdentity) -> object:
        reads.append(entity.name)
        return read_shape(self, entity)

    monkeypatch.setattr(type(facet), "shape", counting)
    plan = planner.finalize(
        WritePlanningRequest(
            actor_identity=TEST_ACTOR_IDENTITY,
            transaction_instant=instant_at("2024-06-01T00:00:00+00:00"),
            concurrency="optimistic",
            composed_writes=buffered,
        )
    )
    assert reads == ["SpotQuote", "DepositRate"]
    _ = list(plan_steps(plan))
    _ = plan_steps(plan)[len(plan_steps(plan)) - 1]
    assert reads == ["SpotQuote", "DepositRate"]


# --------------------------------------------------------------------------- #
# Settlement decorates each update once, and the claims answered are the      #
# surviving writes' own.                                                      #
# --------------------------------------------------------------------------- #
def _wallet_and_account() -> Metamodel:
    return formed(
        DescriptorMetamodel(entities=(*_MODELS["wallet"].entities, *_MODELS["account"].entities))
    )


def _wallet_update() -> list[_TestAdmittedWrite]:
    return [KeyedWriteInstruction("amend", "Wallet", ({"id": 1, "balance": Decimal("2.00")},))]


def test_audit_decorates_each_update_once_at_settlement_and_never_on_enumeration(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Audit follows topology and precedes freezing: an eager update reaches the
    # strategy once and is frozen as the update it returned, so enumerating the
    # plan again reaches no strategy.
    audit = RecordingAudit()
    monkeypatch.setattr(planning_composition, "NO_AUDIT", audit)
    model = _wallet_and_account()
    plan = build_write_planner(model).finalize(
        WritePlanningRequest(
            actor_identity=TEST_ACTOR_IDENTITY,
            transaction_instant=_INSTANT,
            concurrency="locking",
            composed_writes=observed_buffer(_wallet_update(), model, None),
        )
    )
    assert audit.actors == [TEST_ACTOR_IDENTITY]
    (update,) = audit.updates
    assert plan_steps(plan)[0] is update

    assert list(plan_steps(plan)) == [update]
    assert audit.updates == [update]


def test_audit_finalizes_the_rows_and_closes_temporal_expansion_produced(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Audit follows TOPOLOGY, so what a temporal mutation hands the strategy is
    # what stage 7 expanded it into rather than the one update the buffer
    # carried: its close is decorated and each successor row it produces is
    # finalized, once each, and the frozen plan holds exactly what the hooks
    # returned.
    audit = RecordingAudit()
    monkeypatch.setattr(planning_composition, "NO_AUDIT", audit)
    update = KeyedWriteInstruction(
        "amend",
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
    steps = list(plan_steps(plan))
    assert isinstance(steps[0], PlannedClose)
    assert audit.closes == [steps[0]]
    assert steps[0] is audit.closes[0]
    inserts = [step for step in steps[1:] if isinstance(step, PlannedInsert)]
    assert len(inserts) == len(steps) - 1 >= 1
    assert [id(row) for row in audit.rows] == [id(insert.entries[0]) for insert in inserts]


def test_audit_finalizes_each_part_a_pending_opening_leaves_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # A pending insertion's edits leave it as several new lineages; each is a
    # produced row the strategy finalizes once, and enumerating the plan again
    # hands it nothing more.
    audit = RecordingAudit()
    monkeypatch.setattr(planning_composition, "NO_AUDIT", audit)
    plan = _plan(
        [
            KeyedWriteInstruction(
                "insert",
                "Position",
                ({"id": 5, "acctNum": "P5", "value": Decimal("1.0")},),
                valid_from=dt.datetime(2024, 1, 1, tzinfo=dt.UTC),
            ),
            KeyedWriteInstruction(
                "amendUntil",
                "Position",
                ({"id": 5, "value": Decimal("2.0")},),
                valid_from=dt.datetime(2024, 1, 1, tzinfo=dt.UTC),
                until=dt.datetime(2024, 3, 1, tzinfo=dt.UTC),
            ),
        ],
        _POSITION,
        tx_instant=instant_at("2024-06-01T00:00:00+00:00"),
    )
    entries = [step.entries[0] for step in plan_steps(plan) if isinstance(step, PlannedInsert)]
    assert len(entries) == 2
    assert [id(row) for row in audit.rows] == [id(entry) for entry in entries]
    list(plan_steps(plan))
    assert len(audit.rows) == 2


def test_audit_never_reaches_a_milestone_a_write_keeps_unchanged(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    audit = RecordingAudit()
    monkeypatch.setattr(planning_composition, "NO_AUDIT", audit)
    update = KeyedWriteInstruction(
        "amend",
        "Position",
        ({"id": 5, "value": Decimal("1.0")},),
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
    assert list(plan_steps(plan)) == []
    assert (audit.rows, audit.closes) == ([], [])


def test_audit_states_what_it_adds_to_carried_and_changed_rows_as_executed_assignments(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # A carried head keeps its predecessor's state except where finalization
    # assigns an audit value; a changed successor executes its authored
    # assignments and the audit value together. Both state them explicitly, so
    # what each row persists never has to be inferred.
    stamp = AttributeIdentity(corpus_entity("Position"), "acctNum")
    audit = RecordingAudit(stamps={stamp: "audited"})
    monkeypatch.setattr(planning_composition, "NO_AUDIT", audit)
    update = KeyedWriteInstruction(
        "amendUntil",
        "Position",
        ({"id": 5, "value": Decimal("42.0")},),
        valid_from=dt.datetime(2024, 3, 1, tzinfo=dt.UTC),
        until=dt.datetime(2024, 6, 1, tzinfo=dt.UTC),
    )
    key_ = object_key(update, _POSITION)
    assert key_ is not None
    plan = _plan(
        [update],
        _POSITION,
        observations={key_: _bitemporal_observation()},
        tx_instant=instant_at("2024-07-01T00:00:00+00:00"),
    )
    entries = [step.entries[0] for step in plan_steps(plan) if isinstance(step, PlannedInsert)]
    origins = [type(entry.origin).__name__ for entry in entries]
    assert origins == ["CarriedFrom", "ChangedFrom", "CarriedFrom"]
    executed = [
        {cast("AttributeIdentity", member).name for member in entry.executed} for entry in entries
    ]
    assert executed == [{"acctNum"}, {"acctNum", "value"}, {"acctNum"}]
    assert all(entry.row.attributes[stamp] == "audited" for entry in entries)


@pytest.mark.parametrize("member", ["id", "validStart", "validEnd", "txStart", "txEnd"])
def test_audit_may_not_state_a_temporal_rows_key_or_bounds(
    monkeypatch: pytest.MonkeyPatch, member: str
) -> None:
    stamp = AttributeIdentity(corpus_entity("Position"), member)
    monkeypatch.setattr(planning_composition, "NO_AUDIT", RecordingAudit(stamps={stamp: 999}))
    update = KeyedWriteInstruction(
        "amend",
        "Position",
        ({"id": 5, "value": Decimal("42.0")},),
        valid_from=dt.datetime(2024, 3, 1, tzinfo=dt.UTC),
    )
    key_ = object_key(update, _POSITION)
    assert key_ is not None
    with pytest.raises(WritePlanningError, match="state no primary key, temporal bound"):
        _plan(
            [update],
            _POSITION,
            observations={key_: _bitemporal_observation()},
            tx_instant=instant_at("2024-06-01T00:00:00+00:00"),
        )


def test_audit_may_not_state_an_updated_rows_key(monkeypatch: pytest.MonkeyPatch) -> None:
    stamp = AttributeIdentity(corpus_entity("Wallet"), "id")
    monkeypatch.setattr(planning_composition, "NO_AUDIT", RecordingAudit(stamps={stamp: 999}))
    model = _wallet_and_account()
    with pytest.raises(WritePlanningError, match="an update's decoration"):
        _plan(_wallet_update(), model)


def test_only_surviving_writes_carry_their_sources_into_settled_writes() -> None:
    # Two surviving writes settle against one observed state — a destruction and
    # an assignment of one state are a pair no verb admitted as combinable, so
    # both are left standing — and each one's settled write keeps its own
    # source and publishes its own outcome. A write the earlier stages retire
    # takes its source out of the flush with it: the key-only update below is
    # known no-op work, eliminated at stage 2, and never settled, so its source
    # is absent by ABSENCE rather than by a second filter.
    one = corpus_object_key("Account", ("id", 1))
    state = VersionedObjectStateKey(one, 7)
    shared = RetainedObservation(state, VersionObservation(observed_version=7), None)
    retired_observation = VersionObservation(observed_version=4)
    retired = RetainedObservation(
        VersionedObjectStateKey(corpus_object_key("Account", ("id", 2)), 4),
        retired_observation,
        None,
    )
    sources = [
        ReadEvidence(one.entity, one, ParticipationToken(), shared),
        ReadEvidence(one.entity, one, ParticipationToken(), shared),
        ReadEvidence(retired.key.object.entity, retired.key.object, ParticipationToken(), retired),
    ]
    buffer = [
        dataclasses.replace(
            _observed(KeyedWriteInstruction("delete", "Account", ({"id": 1},)), shared),
            source_evidence=(sources[0],),
        ),
        dataclasses.replace(
            _observed(
                KeyedWriteInstruction("amend", "Account", ({"id": 1, "balance": Decimal("9.00")},)),
                shared,
            ),
            source_evidence=(sources[1],),
        ),
        dataclasses.replace(
            _observed(KeyedWriteInstruction("amend", "Account", ({"id": 2},)), retired),
            source_evidence=(sources[2],),
        ),
    ]
    finalized = build_write_planner(_ACCOUNT).finalize(
        WritePlanningRequest(
            actor_identity=TEST_ACTOR_IDENTITY,
            transaction_instant=_INSTANT,
            concurrency="locking",
            composed_writes=buffer,
        )
    )
    assert [_step_mutation(step) for step in plan_steps(finalized)] == ["update", "delete"]
    update, delete = settled_writes(finalized)
    assert isinstance(update, SettledWriteWithSource)
    assert isinstance(delete, SettledWriteWithSource)
    assert (update.source_evidence, delete.source_evidence) == ((sources[1],), (sources[0],))
    assert [
        (tuple(write.changed), write.advanced, write.destroyed) for write in (update, delete)
    ] == [((state,), (state,), ()), ((state,), (), (one,))]


# --------------------------------------------------------------------------- #
# Settlement's own refusals judge the rows a prepared instruction holds. Each #
# instruction below is derived from a prepared one through the planner's own  #
# controlled derivation, which retains rows without re-admitting them.        #
# --------------------------------------------------------------------------- #
def _derived(
    write: KeyedWriteInstruction, model: Metamodel, rows: tuple[Mapping[str, object], ...]
) -> PreparedKeyedInstruction:
    """A prepared keyed write whose rows no ingress would have produced."""
    return derive_keyed_instruction(_prepared_keyed(write, model), rows)


def test_a_preformed_plural_temporal_update_of_key_only_rows_reaches_settlement_whole() -> None:
    # Elimination never takes a plural temporal instruction apart, even where
    # every row names only its key: it reaches settlement as authored, which
    # refuses it rather than planning nothing.
    plural = _derived(
        KeyedWriteInstruction("amend", "Balance", ({"id": 1, "value": Decimal("9.00")},)),
        _BALANCE,
        rows=({"id": 1}, {"id": 2}),
    )
    with pytest.raises(WritePlanningError, match="every close requires the Temporal Observation"):
        _plan([plural], _BALANCE)


def test_a_row_naming_a_member_outside_the_family_is_refused_at_settlement() -> None:
    stray = _derived(
        KeyedWriteInstruction(
            "insert", "Wallet", ({"id": 1, "owner": "Ada", "balance": Decimal("1.00")},)
        ),
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
        KeyedWriteInstruction(
            "insert", "Wallet", ({"id": 1, "owner": "Ada", "balance": Decimal("1.00")},)
        ),
        _WALLET,
        rows=({"id": 1, "owner": document, "balance": Decimal("1.00")},),
    )
    (step,) = plan_steps(_plan([carried], _WALLET))
    assert _insert_rows(step)[0]["owner"] == document
