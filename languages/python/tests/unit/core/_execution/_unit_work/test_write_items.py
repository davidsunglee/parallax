"""Admitted writes: each holds only what licenses it (m-unit-work, Docker-free)."""

from __future__ import annotations

from collections.abc import Mapping
from decimal import Decimal
from typing import TYPE_CHECKING

import pytest

from parallax.core._execution._unit_work.acquisition import RetainedTargetState
from parallax.core._execution._unit_work.claims import WriteIntent
from parallax.core._execution._unit_work.evidence import (
    InsertionIdentity,
    ParticipationToken,
    ReadEvidence,
)
from parallax.core._execution._unit_work.instructions import (
    ExpectedTxStart,
    PreparedKeyedInstruction,
    prepare_typed_write,
    prepare_wire_write,
)
from parallax.core._execution._unit_work.write_items import (
    AdmittedWrite,
    ComposedBitemporalOpening,
    ComposedTemporalWrite,
    ComposedWrite,
    InsertBatch,
    InsertionAuthorizedIntent,
    InsertionAuthorizedWrite,
    KeyedInsert,
    ObjectLockedBatch,
    ObjectLockedWrite,
    OrderedWrite,
    PostRemovalInsert,
    StateObservedIntent,
    StateObservedWrite,
    TargetIntent,
    TargetWrite,
    TemporalCoverageWrite,
    TemporalIntent,
    WritePhase,
)
from parallax.core.metamodel import CompiledEntity
from parallax.core.temporal_write.coverage import CoverageTransform
from parallax.core.unit_work import (
    KeyedMutation,
    KeyedWriteInstruction,
    RetainedObservation,
    admitted_write,
    object_key,
)
from parallax.core.write_plan import ObjectKey, VersionObservation
from parallax.core.write_plan.keys import VersionedObjectStateKey
from tests._support.planner_probes import admitted_writes, write_admission
from tests._support.write_preparation import write_preparation_of
from tests.unit._corpus_model_support import model as corpus_model
from tests.unit.core._execution._unit_work._temporal_targets_support import (
    JAN,
    JUN,
    MAR,
    OBJECT,
    POSITION,
    SEP,
    observed_write,
    rectangle,
    retained,
)

_ACCOUNT = corpus_model("account")


def _prepared(mutation: KeyedMutation, *rows: Mapping[str, object]) -> PreparedKeyedInstruction:
    prepared = prepare_typed_write(
        KeyedWriteInstruction(mutation, "Account", rows), write_preparation_of(_ACCOUNT)
    )
    assert isinstance(prepared, PreparedKeyedInstruction)
    return prepared


def _account(account_id: int) -> dict[str, object]:
    return {"id": account_id, "owner": "Ada", "balance": Decimal("1.00")}


def _account_key(account_id: int) -> ObjectKey:
    key = object_key(_prepared("delete", {"id": account_id}), _ACCOUNT)
    assert key is not None
    return key


def test_an_insert_is_admitted_as_its_own_keyed_insert() -> None:
    prepared = _prepared("insert", _account(1))
    admitted = admitted_write(prepared, None, object_key(prepared, _ACCOUNT))
    assert isinstance(admitted, KeyedInsert)
    assert admitted.instruction is prepared
    assert admitted.object_key == _account_key(1)


@pytest.mark.parametrize(
    ("mutation", "row"),
    [("amend", {"id": 1, "balance": Decimal("2.00")}), ("delete", {"id": 1})],
)
def test_a_write_of_existing_state_needs_a_licence_beyond_itself(
    mutation: KeyedMutation, row: Mapping[str, object]
) -> None:
    with pytest.raises(ValueError, match="only an insert is admitted unlicensed"):
        admitted_write(_prepared(mutation, row), None, None)


def test_an_admitted_insert_opens_one_row() -> None:
    with pytest.raises(ValueError, match="opens 2 rows"):
        admitted_write(_prepared("insert", _account(1), _account(2)), None, None)


@pytest.mark.parametrize(
    "licence",
    ["observed", "insertion"],
)
def test_a_licensed_write_names_the_object_it_writes(licence: str) -> None:
    prepared = _prepared("amend", {"id": 1, "balance": Decimal("2.00")})
    key = _account_key(1)
    with pytest.raises(ValueError, match="names the object it writes"):
        if licence == "observed":
            observed = RetainedObservation(
                VersionedObjectStateKey(key, 4), VersionObservation(4), None
            )
            admitted_write(prepared, observed, None)
        else:
            admitted_write(prepared, None, None, authority=InsertionIdentity(key))


def test_a_composed_opening_names_the_object_its_insert_names() -> None:
    assert _position_opening().object_key == OBJECT


def test_a_post_removal_insert_answers_its_inserts_phase_and_target() -> None:
    insert = admitted_write(_prepared("insert", _account(1)), None, _account_key(1))
    assert isinstance(insert, KeyedInsert)
    marker = PostRemovalInsert(insert)
    assert (marker.phase, marker.target) == ("insert", insert.instruction.target)


def _position_opening() -> ComposedBitemporalOpening:
    insertion = prepare_wire_write(
        KeyedWriteInstruction(
            "insertUntil", "Position", ({"id": 1, "acctNum": "A", "value": "1.00"},), JAN, SEP
        ),
        write_preparation_of(POSITION),
    )
    amendment = prepare_wire_write(
        KeyedWriteInstruction("amendUntil", "Position", ({"id": 1, "value": "2.00"},), JAN, MAR),
        write_preparation_of(POSITION),
    )
    assert isinstance(insertion, PreparedKeyedInstruction)
    assert isinstance(amendment, PreparedKeyedInstruction)
    admission = write_admission(POSITION)
    identity = admission.admit_insert(
        admitted_write(insertion, None, OBJECT), insertion_advice=None
    )
    assert identity is not None
    admission.admit(
        admitted_write(amendment, None, OBJECT, authority=identity), confirm_target=_confirmed
    )
    (opening,) = admission.composed_writes()
    assert isinstance(opening, ComposedBitemporalOpening)
    return opening


def _confirmed(write: TargetWrite) -> TargetWrite:
    return write


def test_a_composed_temporal_write_keeps_equal_but_distinct_evidence_once_each_in_order() -> None:
    first = retained(rectangle(JAN, JUN, "1.00"))
    second = retained(rectangle(JUN, SEP, "2.00"))
    earlier = observed_write("amendUntil", first, valid_from=MAR, until=JUN, value="3.00")
    repeated = observed_write("amendUntil", first, valid_from=MAR, until=JUN, value="4.00")
    later = observed_write("amendUntil", second, valid_from=JUN, until=SEP, value="5.00")
    participation = ParticipationToken()
    twin = ReadEvidence(OBJECT.entity, OBJECT, participation, first)
    equal = ReadEvidence(OBJECT.entity, OBJECT, participation, first)
    assert twin == equal and twin is not equal
    writes = [
        StateObservedWrite(
            w.instruction, w.object_key, w.retained_observation, source_evidence=(e,)
        )
        for w, e in ((earlier, twin), (repeated, twin), (later, equal))
    ]
    (composed,) = admitted_writes(POSITION, writes)
    assert isinstance(composed, ComposedTemporalWrite)
    kept = composed.source_evidence
    assert len(kept) == 2 and kept[0] is twin and kept[1] is equal


if TYPE_CHECKING:

    def _static_projection_contract(  # pyright: ignore[reportUnusedFunction] - static contract probe
        insert: KeyedInsert,
        observed: StateObservedWrite,
        locked: ObjectLockedWrite,
        authorized: InsertionAuthorizedWrite,
        targeted: TargetWrite,
        insert_batch: InsertBatch,
        locked_batch: ObjectLockedBatch,
        composed: ComposedTemporalWrite,
        opening: ComposedBitemporalOpening,
        marker: PostRemovalInsert,
        admitted: AdmittedWrite,
        composed_write: ComposedWrite,
        ordered: OrderedWrite,
        observed_intent: StateObservedIntent,
        authorized_intent: InsertionAuthorizedIntent,
        target_intent: TargetIntent,
        intent: TemporalIntent,
        coverage: TemporalCoverageWrite,
    ) -> None:
        instruction: PreparedKeyedInstruction = admitted.instruction
        key: ObjectKey | None = admitted.object_key
        keys: tuple[ObjectKey | None, ...] = insert_batch.object_keys
        locked_keys: tuple[ObjectKey, ...] = locked_batch.object_keys
        composed_key: ObjectKey = composed.object_key
        opening_key: ObjectKey | None = opening.object_key
        evidence: tuple[ReadEvidence, ...] = ordered.source_evidence
        phase: WritePhase = composed_write.phase
        target: CompiledEntity = composed_write.target
        scope = (
            observed.claim_scope,
            locked.claim_scope,
            authorized.claim_scope,
            targeted.claim_scope,
        )
        del instruction, key, keys, locked_keys, composed_key, opening_key, evidence
        del phase, target, scope
        intents: tuple[TemporalIntent, ...] = composed.intents
        opening_intents: tuple[WriteIntent, ...] = opening.intents
        stated: WriteIntent = intent.intent
        observation: RetainedObservation = observed_intent.retained_observation
        observed_evidence: tuple[ReadEvidence, ...] = observed_intent.source_evidence
        expected: ExpectedTxStart = target_intent.expected
        retained_row: RetainedTargetState | None = target_intent.retained
        del intents, opening_intents, stated, observation, observed_evidence, expected
        del retained_row
        pending_intents: tuple[TemporalIntent, ...] = coverage.intents
        pending_transform: CoverageTransform = coverage.transform
        pending_key: ObjectKey = coverage.object_key
        pending_target: CompiledEntity = coverage.target
        del pending_intents, pending_transform, pending_key, pending_target
        _ = coverage.instruction  # pyright: ignore[reportAttributeAccessIssue,reportUnknownMemberType,reportUnknownVariableType] - a composition holds no one instruction
        _ = locked.intents  # pyright: ignore[reportAttributeAccessIssue,reportUnknownMemberType,reportUnknownVariableType] - an object-locked row is no temporal write
        _ = admitted.intents  # pyright: ignore[reportAttributeAccessIssue,reportUnknownMemberType,reportUnknownVariableType] - an insert composes nothing
        _ = composed_write.intents  # pyright: ignore[reportAttributeAccessIssue,reportUnknownMemberType,reportUnknownVariableType] - inserts and markers keep none
        _ = observed_intent.expected  # pyright: ignore[reportAttributeAccessIssue,reportUnknownMemberType,reportUnknownVariableType] - a read states no caller's start
        _ = observed_intent.retained  # pyright: ignore[reportAttributeAccessIssue,reportUnknownMemberType,reportUnknownVariableType] - a read retains no starting row
        _ = authorized_intent.retained_observation  # pyright: ignore[reportAttributeAccessIssue,reportUnknownMemberType,reportUnknownVariableType] - an insertion observed nothing
        _ = authorized_intent.source_evidence  # pyright: ignore[reportAttributeAccessIssue,reportUnknownMemberType,reportUnknownVariableType] - insertion authority is no Read Evidence
        _ = authorized_intent.expected  # pyright: ignore[reportAttributeAccessIssue,reportUnknownMemberType,reportUnknownVariableType] - an insertion states no caller's start
        _ = target_intent.retained_observation  # pyright: ignore[reportAttributeAccessIssue,reportUnknownMemberType,reportUnknownVariableType] - a caller's condition observed nothing
        _ = target_intent.source_evidence  # pyright: ignore[reportAttributeAccessIssue,reportUnknownMemberType,reportUnknownVariableType] - a caller's condition is no Read Evidence
        _ = intent.retained_observation  # pyright: ignore[reportAttributeAccessIssue,reportUnknownMemberType,reportUnknownVariableType] - only an observed intent observed
        _ = intent.source_evidence  # pyright: ignore[reportAttributeAccessIssue,reportUnknownMemberType,reportUnknownVariableType] - only an observed intent holds evidence
        _ = intent.expected  # pyright: ignore[reportAttributeAccessIssue,reportUnknownMemberType,reportUnknownVariableType] - only a target intent states a start
        _ = insert.claim_scope  # pyright: ignore[reportAttributeAccessIssue,reportUnknownMemberType,reportUnknownVariableType] - an insert claims nothing
        _ = insert_batch.object_key  # pyright: ignore[reportAttributeAccessIssue,reportUnknownMemberType,reportUnknownVariableType] - a batch names several objects
        _ = insert_batch.claim_scope  # pyright: ignore[reportAttributeAccessIssue,reportUnknownMemberType,reportUnknownVariableType] - a batch claims nothing
        _ = locked_batch.object_key  # pyright: ignore[reportAttributeAccessIssue,reportUnknownMemberType,reportUnknownVariableType] - a batch names several objects
        _ = locked_batch.claim_scope  # pyright: ignore[reportAttributeAccessIssue,reportUnknownMemberType,reportUnknownVariableType] - a batch claims nothing
        _ = composed.instruction  # pyright: ignore[reportAttributeAccessIssue,reportUnknownMemberType,reportUnknownVariableType] - a composition holds no one instruction
        _ = composed.claim_scope  # pyright: ignore[reportAttributeAccessIssue,reportUnknownMemberType,reportUnknownVariableType] - a composition composes by object
        _ = opening.instruction  # pyright: ignore[reportAttributeAccessIssue,reportUnknownMemberType,reportUnknownVariableType] - an opening holds its insert instead
        _ = marker.instruction  # pyright: ignore[reportAttributeAccessIssue,reportUnknownMemberType,reportUnknownVariableType] - ordering unwraps the marker
        _ = marker.object_key  # pyright: ignore[reportAttributeAccessIssue,reportUnknownMemberType,reportUnknownVariableType] - ordering unwraps the marker
        _ = marker.claim_scope  # pyright: ignore[reportAttributeAccessIssue,reportUnknownMemberType,reportUnknownVariableType] - ordering unwraps the marker
        _ = marker.source_evidence  # pyright: ignore[reportAttributeAccessIssue,reportUnknownMemberType,reportUnknownVariableType] - ordering unwraps the marker
        _ = admitted.claim_scope  # pyright: ignore[reportAttributeAccessIssue,reportUnknownMemberType,reportUnknownVariableType] - an admitted insert claims nothing
        _ = composed_write.instruction  # pyright: ignore[reportAttributeAccessIssue,reportUnknownMemberType,reportUnknownVariableType] - compositions hold none
        _ = composed_write.object_key  # pyright: ignore[reportAttributeAccessIssue,reportUnknownMemberType,reportUnknownVariableType] - the marker names none
        _ = composed_write.source_evidence  # pyright: ignore[reportAttributeAccessIssue,reportUnknownMemberType,reportUnknownVariableType] - the marker holds none
        _ = ordered.instruction  # pyright: ignore[reportAttributeAccessIssue,reportUnknownMemberType,reportUnknownVariableType] - compositions hold none
        _ = ordered.object_key  # pyright: ignore[reportAttributeAccessIssue,reportUnknownMemberType,reportUnknownVariableType] - batches name several objects
        unordered: OrderedWrite = marker  # pyright: ignore[reportAssignmentType] - ordering consumes markers
        unbatched: ComposedWrite = insert_batch  # pyright: ignore[reportAssignmentType] - only batching batches
        uncomposed: AdmittedWrite = composed  # pyright: ignore[reportAssignmentType] - only admission composes
        del unordered, unbatched, uncomposed
