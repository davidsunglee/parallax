"""Admitted writes: each holds only what licenses it (m-unit-work, Docker-free)."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from decimal import Decimal
from typing import TYPE_CHECKING, Final, cast

import pytest

from parallax.core import inheritance
from parallax.core._execution._unit_work.admission import WriteAdmission
from parallax.core._execution._unit_work.instructions import (
    PreparedKeyedInstruction,
    derive_keyed_instruction,
    prepare_typed_write,
    prepare_wire_write,
)
from parallax.core._execution._unit_work.retain import (
    InsertionIdentity,
    ParticipationToken,
    ReadEvidence,
)
from parallax.core._execution._unit_work.write_items import (
    AdmittedWrite,
    ComposedBitemporalOpening,
    ComposedTemporalWrite,
    ComposedWrite,
    InsertBatch,
    InsertionAuthorizedWrite,
    KeyedInsert,
    ObjectLockedBatch,
    ObjectLockedWrite,
    OrderedWrite,
    PostRemovalInsert,
    StateObservedWrite,
    TargetWrite,
    WritePhase,
    target_write,
)
from parallax.core.metamodel import EntityMetadata
from parallax.core.unit_work import (
    KeyedMutation,
    KeyedWriteInstruction,
    RetainedObservation,
    TargetWriteInstruction,
    admitted_write,
    object_key,
)
from parallax.core.write_plan import ObjectKey, VersionObservation
from parallax.core.write_plan.keys import VersionedObjectStateKey
from tests._support.planner_probes import admitted_writes, object_source
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
_PERSON = corpus_model("person")


def _prepared(mutation: KeyedMutation, *rows: Mapping[str, object]) -> PreparedKeyedInstruction:
    prepared = prepare_typed_write(KeyedWriteInstruction(mutation, "Account", rows), _ACCOUNT)
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


# --------------------------------------------------------------------------- #
# The projection matrix: what every write answers of itself.                  #
# --------------------------------------------------------------------------- #
_ABSENT: Final = object()
"""A cell a write type does not answer, which the static probes below prove."""


@dataclass(frozen=True, slots=True)
class _Row:
    """One write and the projections it answers, each beside what it answers
    with."""

    write: object
    instruction: object
    object_key: object
    claim_scope: object
    source_evidence: object
    phase: WritePhase
    target: EntityMetadata

    def answered(self) -> dict[str, object]:
        cells = {
            "instruction": self.instruction,
            "object_key": self.object_key,
            "claim_scope": self.claim_scope,
            "source_evidence": self.source_evidence,
            "phase": self.phase,
            "target": self.target,
        }
        return {name: value for name, value in cells.items() if value is not _ABSENT}


def _keyed_insert() -> _Row:
    write = admitted_write(_prepared("insert", _account(1)), None, _account_key(1))
    assert isinstance(write, KeyedInsert)
    return _Row(write, write.instruction, _account_key(1), _ABSENT, (), "insert", _target(write))


def _absent_key_insert() -> _Row:
    write = KeyedInsert(_prepared("insert", _account(1)), None)
    return _Row(write, write.instruction, None, _ABSENT, (), "insert", _target(write))


def _state_observed() -> _Row:
    key = _account_key(1)
    observed = RetainedObservation(VersionedObjectStateKey(key, 4), VersionObservation(4), None)
    source = ReadEvidence(key.entity, key, ParticipationToken(), observed)
    write = admitted_write(
        _prepared("amend", {"id": 1, "balance": Decimal("2.00")}), observed, key, source=source
    )
    assert isinstance(write, StateObservedWrite)
    return _Row(write, write.instruction, key, observed.key, (source,), "update", _target(write))


def _continued_state_observed() -> _Row:
    key = _account_key(1)
    observed = RetainedObservation(VersionedObjectStateKey(key, 4), VersionObservation(4), None)
    source = ReadEvidence(key.entity, key, ParticipationToken(), observed)
    advanced = VersionedObjectStateKey(key, 5)
    write = admitted_write(_prepared("delete", {"id": 1}), advanced, key, source=source)
    assert isinstance(write, StateObservedWrite)
    return _Row(write, write.instruction, key, advanced, (source,), "delete", _target(write))


def _person_delete(*person_ids: int) -> PreparedKeyedInstruction:
    prepared = prepare_typed_write(
        KeyedWriteInstruction("delete", "Person", tuple({"id": key} for key in person_ids)),
        _PERSON,
    )
    assert isinstance(prepared, PreparedKeyedInstruction)
    return prepared


def _person_key(person_id: int) -> ObjectKey:
    key = object_key(_person_delete(person_id), _PERSON)
    assert key is not None
    return key


def _object_locked() -> _Row:
    key = _person_key(1)
    source = object_source(key)
    write = admitted_write(_person_delete(1), key, key, source=source)
    assert isinstance(write, ObjectLockedWrite)
    return _Row(write, write.instruction, key, key, (source,), "delete", _target(write))


def _insertion_authorized() -> _Row:
    key = _account_key(1)
    write = admitted_write(
        _prepared("amend", {"id": 1, "balance": Decimal("2.00")}),
        None,
        key,
        authority=InsertionIdentity(key),
    )
    assert isinstance(write, InsertionAuthorizedWrite)
    return _Row(write, write.instruction, key, None, (), "update", _target(write))


def _target_write() -> _Row:
    prepared = prepare_wire_write(
        TargetWriteInstruction("delete", "Account", {"id": 1}, if_version=3), _ACCOUNT
    )
    write = target_write(prepared, inheritance.view(_ACCOUNT))
    key = _account_key(1)
    return _Row(
        write,
        write.instruction,
        key,
        VersionedObjectStateKey(key, 3),
        (),
        "delete",
        _target(write),
    )


def _insert_batch() -> _Row:
    first, second = (_prepared("insert", _account(key)) for key in (1, 2))
    merged = derive_keyed_instruction(first, (*first.rows, *second.rows))
    keys = (_account_key(1), _account_key(2))
    write = InsertBatch(merged, keys)
    return _Row(write, merged, _ABSENT, _ABSENT, (), "insert", _target(write))


def _object_locked_batch() -> _Row:
    keys = (_person_key(1), _person_key(2))
    evidence = tuple(object_source(key) for key in keys)
    merged = _person_delete(1, 2)
    write = ObjectLockedBatch(merged, keys, evidence)
    return _Row(write, merged, _ABSENT, _ABSENT, evidence, "delete", _target(write))


def _composed_temporal(*, assigns: bool) -> _Row:
    earlier, later = retained(rectangle(JAN, JUN, "1.00")), retained(rectangle(JUN, SEP, "2.00"))
    mutation: KeyedMutation = "amendUntil" if assigns else "terminateUntil"
    members = {"value": "3.00"} if assigns else {}
    first = observed_write(mutation, earlier, valid_from=MAR, until=JUN, **members)
    second = observed_write(mutation, later, valid_from=JUN, until=SEP, **members)
    (write,) = admitted_writes(POSITION, [first, second])
    assert isinstance(write, ComposedTemporalWrite)
    evidence = (*first.source_evidence, *second.source_evidence)
    return _Row(
        write,
        _ABSENT,
        OBJECT,
        _ABSENT,
        evidence,
        "update" if assigns else "delete",
        write.target,
    )


def _position_opening() -> ComposedBitemporalOpening:
    insertion = prepare_wire_write(
        KeyedWriteInstruction(
            "insertUntil", "Position", ({"id": 1, "acctNum": "A", "value": "1.00"},), JAN, SEP
        ),
        POSITION,
    )
    amendment = prepare_wire_write(
        KeyedWriteInstruction("amendUntil", "Position", ({"id": 1, "value": "2.00"},), JAN, MAR),
        POSITION,
    )
    assert isinstance(insertion, PreparedKeyedInstruction)
    assert isinstance(amendment, PreparedKeyedInstruction)
    admission = WriteAdmission(POSITION, inserted_version=_no_version, observations={})
    admission.admit(admitted_write(insertion, None, OBJECT), confirm_target=_confirmed)
    identity = admission.insertion_identity(OBJECT)
    assert identity is not None
    admission.admit(
        admitted_write(amendment, None, OBJECT, authority=identity), confirm_target=_confirmed
    )
    (opening,) = admission.composed_writes()
    assert isinstance(opening, ComposedBitemporalOpening)
    return opening


def _opening() -> _Row:
    write = _position_opening()
    return _Row(write, _ABSENT, OBJECT, _ABSENT, (), "insert", write.insert.instruction.target)


def _post_removal_insert() -> _Row:
    insert = admitted_write(_prepared("insert", _account(1)), None, _account_key(1))
    assert isinstance(insert, KeyedInsert)
    write = PostRemovalInsert(insert)
    return _Row(write, _ABSENT, _ABSENT, _ABSENT, _ABSENT, "insert", _target(insert))


def _target(write: AdmittedWrite | InsertBatch | ObjectLockedBatch) -> EntityMetadata:
    return write.instruction.target


def _no_version(*_: object) -> int | None:
    return None


def _confirmed(write: TargetWrite) -> TargetWrite:
    return write


_MATRIX: Final[Mapping[str, Callable[[], _Row]]] = {
    "keyed-insert": _keyed_insert,
    "keyed-insert-absent-key": _absent_key_insert,
    "state-observed": _state_observed,
    "state-observed-continued": _continued_state_observed,
    "object-locked": _object_locked,
    "insertion-authorized": _insertion_authorized,
    "target": _target_write,
    "insert-batch": _insert_batch,
    "object-locked-batch": _object_locked_batch,
    "composed-temporal-assigning": lambda: _composed_temporal(assigns=True),
    "composed-temporal-destroying": lambda: _composed_temporal(assigns=False),
    "composed-bitemporal-opening": _opening,
    "post-removal-insert": _post_removal_insert,
}


@pytest.mark.parametrize("row", list(_MATRIX.values()), ids=list(_MATRIX))
def test_every_write_answers_its_own_projections(row: Callable[[], _Row]) -> None:
    built = row()
    for projection, expected in built.answered().items():
        assert getattr(built.write, projection) == expected, projection


@pytest.mark.parametrize(
    "row", [_state_observed, _object_locked, _object_locked_batch], ids=lambda r: r.__name__
)
def test_retained_source_evidence_is_the_admitted_objects_themselves(
    row: Callable[[], _Row],
) -> None:
    built = row()
    write = built.write
    assert isinstance(write, StateObservedWrite | ObjectLockedWrite | ObjectLockedBatch)
    expected = cast("tuple[ReadEvidence, ...]", built.source_evidence)
    assert len(write.source_evidence) == len(expected)
    assert all(held is kept for held, kept in zip(write.source_evidence, expected, strict=True))


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
    ) -> None:
        instruction: PreparedKeyedInstruction = admitted.instruction
        key: ObjectKey | None = admitted.object_key
        keys: tuple[ObjectKey | None, ...] = insert_batch.object_keys
        locked_keys: tuple[ObjectKey, ...] = locked_batch.object_keys
        composed_key: ObjectKey = composed.object_key
        opening_key: ObjectKey | None = opening.object_key
        evidence: tuple[ReadEvidence, ...] = ordered.source_evidence
        phase: WritePhase = composed_write.phase
        target: EntityMetadata = composed_write.target
        scope = (
            observed.claim_scope,
            locked.claim_scope,
            authorized.claim_scope,
            targeted.claim_scope,
        )
        del instruction, key, keys, locked_keys, composed_key, opening_key, evidence
        del phase, target, scope
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
