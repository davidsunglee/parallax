"""Write admission (`m-unit-work` "Observed-State Coalescing"), observed at the
owner's interface where the write verbs cannot say it precisely: when a
target write's confirmation is consulted, how a planned buffer drains into the
live ownership, and the window rules a temporal object's target
writes meet that the verb matrices do not reach. What a caller sees through
the verbs is the snapshot and API suites'."""

from __future__ import annotations

import dataclasses
import datetime as dt
from collections.abc import Iterator
from decimal import Decimal

import pytest

from parallax.conformance.class_models import MODELS as CLASS_MODELS
from parallax.core import inheritance
from parallax.core._execution._unit_work._write_ownership import SourceRefusal
from parallax.core._execution._unit_work.admission import BufferOutcome, WriteAdmission
from parallax.core._execution._unit_work.instructions import (
    ExpectedTxStart,
    PreparedKeyedInstruction,
    prepare_wire_write,
)
from parallax.core._execution._unit_work.retain import (
    ParticipationToken,
    ReadEvidence,
    RetainedTargetState,
)
from parallax.core._execution._unit_work.write_items import (
    AdmittedWrite,
    ComposedTemporalWrite,
    InsertionAuthorizedWrite,
    KeyedInsert,
    ObjectLockedWrite,
    PostRemovalInsert,
    TargetWrite,
    target_write,
)
from parallax.core.base import INFINITY
from parallax.core.entity._model import model_of
from parallax.core.metamodel import EntityIdentity, Metamodel
from parallax.core.unit_work import (
    KeyedWriteInstruction,
    RetainedObservation,
    TargetWriteInstruction,
    WriteEvidenceError,
    admitted_write,
)
from parallax.core.write_plan import (
    ObjectKey,
    VersionObservation,
)
from parallax.core.write_plan.keys import (
    ObjectStateKey,
    TemporalObjectStateKey,
    VersionedObjectStateKey,
)
from parallax.core.write_plan.plan import (
    OPEN_BITEMPORAL_ENDS,
    AllocatedOpening,
    Openings,
    TemporalRowCoordinates,
    WriteEffects,
)
from parallax.core.write_plan.steps import INFINITY as PLANNED_INFINITY
from parallax.core.write_plan.steps import Finite
from tests._support.planner_probes import object_source
from tests.unit._corpus_model_support import corpus_records, formed
from tests.unit.core._execution._unit_work._temporal_targets_support import (
    APR,
    AUG,
    ENTITY,
    FEB,
    JAN,
    JUL,
    JUN,
    MAR,
    MAY,
    OBJECT,
    OCT,
    POSITION,
    RESTATED,
    SEP,
    START,
    T0,
    T1,
    WHOLE,
    addressed_write,
    observed_write,
    rectangle,
    retained,
)

_ACCOUNT = formed(corpus_records()["account"])
_ACCOUNT_ENTITY = EntityIdentity("parallax.compatibility", "Account")
_PERSON = model_of(CLASS_MODELS["person"])
_PERSON_ENTITY = EntityIdentity("parallax.compatibility", "Person")
_WALLET = formed(corpus_records()["wallet"])
_INSERTED_AT = dt.datetime(2024, 1, 10, tzinfo=dt.UTC)


def _confirmed(item: TargetWrite) -> TargetWrite:
    return item


def _unversioned(entity: EntityIdentity, advanced_from: int | None) -> int | None:
    del entity, advanced_from
    return None


def _admitted(*writes: AdmittedWrite, meta: Metamodel = POSITION) -> WriteAdmission:
    admission = WriteAdmission(meta, inserted_version=_unversioned, observations={})
    for write in writes:
        admission.admit(write, confirm_target=_confirmed)
    return admission


def _admit(admission: WriteAdmission, *writes: AdmittedWrite) -> None:
    for write in writes:
        admission.admit(write, confirm_target=_confirmed)


def _refused(admission: WriteAdmission, write: AdmittedWrite) -> None:
    with pytest.raises(WriteEvidenceError) as refusal:
        admission.admit(write, confirm_target=_confirmed)
    assert refusal.value.code == "write-evidence-already-claimed"


def _account(account_id: int) -> ObjectKey:
    return ObjectKey(_ACCOUNT_ENTITY, (("id", account_id),))


def _account_observed(account_id: int, version: int) -> AdmittedWrite:
    prepared = prepare_wire_write(
        KeyedWriteInstruction("amend", "Account", ({"id": account_id, "owner": "Bo"},)), _ACCOUNT
    )
    assert isinstance(prepared, PreparedKeyedInstruction)
    state = VersionedObjectStateKey(_account(account_id), version)
    return admitted_write(prepared, RetainedObservation(state, VersionObservation(version), None))


def _account_target(account_id: int, version: int) -> TargetWrite:
    prepared = prepare_wire_write(
        TargetWriteInstruction(
            "amend", "Account", {"id": account_id, "balance": "1.00"}, if_version=version
        ),
        _ACCOUNT,
    )
    return target_write(prepared, inheritance.view(_ACCOUNT))


def _account_insert(account_id: int) -> AdmittedWrite:
    prepared = prepare_wire_write(
        KeyedWriteInstruction(
            "insert", "Account", ({"id": account_id, "owner": "N", "balance": "5.00"},)
        ),
        _ACCOUNT,
    )
    assert isinstance(prepared, PreparedKeyedInstruction)
    return admitted_write(prepared, None)


def _account_amend(account_id: int) -> PreparedKeyedInstruction:
    prepared = prepare_wire_write(
        KeyedWriteInstruction("amend", "Account", ({"id": account_id, "owner": "Cy"},)), _ACCOUNT
    )
    assert isinstance(prepared, PreparedKeyedInstruction)
    return prepared


# --------------------------------------------------------------------------- #
# A target write is confirmed once acceptance leaves it unproven.   #
# --------------------------------------------------------------------------- #
class _Confirmations:
    def __init__(self) -> None:
        self.asked: list[TargetWrite] = []

    def __call__(self, item: TargetWrite) -> TargetWrite:
        self.asked.append(item)
        return item


def test_a_pending_write_of_the_targets_state_proves_it_before_confirmation_is_asked() -> None:
    confirm = _Confirmations()
    admission = WriteAdmission(POSITION, inserted_version=_unversioned, observations={})
    first = addressed_write(value="150.00")
    admission.admit(first, confirm_target=confirm)
    # A second write over exactly that window starts from the state the first
    # does; one refused for another stated start is never confirmed.
    admission.admit(addressed_write(value="175.00"), confirm_target=confirm)
    with pytest.raises(WriteEvidenceError):
        admission.admit(addressed_write(tx_start=T1, value="1.00"), confirm_target=confirm)
    assert confirm.asked == [first]

    versioned = WriteAdmission(_ACCOUNT, inserted_version=_unversioned, observations={})
    versioned.admit(_account_observed(1, 3), confirm_target=confirm)
    versioned.admit(_account_target(1, 3), confirm_target=confirm)
    alone = _account_target(2, 3)
    versioned.admit(alone, confirm_target=confirm)
    assert confirm.asked == [first, alone]


def test_an_inserted_objects_target_is_refused_before_its_conflicts_or_confirmation() -> None:
    confirm = _Confirmations()
    admission = WriteAdmission(_ACCOUNT, inserted_version=lambda _entity, _from: 1, observations={})
    admission.admit(_account_insert(1), confirm_target=confirm)
    admission.drain_planned()
    # A pending write of another state of the object would also refuse it.
    admission.admit(_account_observed(1, 1), confirm_target=confirm)
    with pytest.raises(WriteEvidenceError) as refusal:
        admission.admit(_account_target(1, 7), confirm_target=confirm)
    assert refusal.value.code == "write-evidence-inserted"
    assert confirm.asked == []


def test_the_write_confirmation_answers_is_the_one_composed() -> None:
    state = START.key
    assert isinstance(state, TemporalObjectStateKey)
    held = RetainedTargetState(state, 0, (), None)

    def retaining(item: TargetWrite) -> TargetWrite:
        return dataclasses.replace(item, retained=held)

    admission = WriteAdmission(POSITION, inserted_version=_unversioned, observations={})
    admission.admit(addressed_write(value="150.00"), confirm_target=retaining)
    (composed,) = admission.composed_writes()
    assert isinstance(composed, TargetWrite)
    assert composed.retained is held


# --------------------------------------------------------------------------- #
# A planned buffer drains into the live ownership; discard spends nothing.    #
# --------------------------------------------------------------------------- #
def test_a_batch_composition_left_nothing_of_still_needs_its_flush() -> None:
    admission = WriteAdmission(_ACCOUNT, inserted_version=_unversioned, observations={})
    assert not admission
    _admit(admission, _account_insert(9))
    deletion = prepare_wire_write(
        KeyedWriteInstruction("delete", "Account", ({"id": 9},)), _ACCOUNT
    )
    assert isinstance(deletion, PreparedKeyedInstruction)
    identity = admission.insertion_identity(_account(9))
    assert identity is not None
    outcome = admission.admit(
        admitted_write(deletion, None, authority=identity), confirm_target=_confirmed
    )
    assert outcome is BufferOutcome.CANCELLED_PENDING_INSERT
    assert admission
    assert admission.composed_writes() == ()
    admission.drain_planned()
    assert not admission


def test_an_amendment_folded_into_a_pending_insert_leaves_it_an_insert() -> None:
    admission = WriteAdmission(_ACCOUNT, inserted_version=_unversioned, observations={})
    _admit(admission, _account_insert(9))
    identity = admission.insertion_identity(_account(9))
    assert identity is not None
    _admit(admission, admitted_write(_account_amend(9), None, authority=identity))
    (insert,) = admission.composed_writes()
    assert isinstance(insert, KeyedInsert)
    assert insert.instruction.mutation == "insert"
    assert insert.instruction.rows[0]["owner"] == "Cy"


def _person(person_id: int) -> ObjectKey:
    return ObjectKey(_PERSON_ENTITY, (("id", person_id),))


def _person_write(person_id: int, source: ReadEvidence) -> AdmittedWrite:
    prepared = prepare_wire_write(
        KeyedWriteInstruction("amend", "Person", ({"id": person_id, "name": "Grace"},)), _PERSON
    )
    assert isinstance(prepared, PreparedKeyedInstruction)
    return admitted_write(prepared, _person(person_id), source=source)


def test_coalesced_object_locked_writes_keep_every_distinct_source_evidence() -> None:
    participation = ParticipationToken()
    first, other, coalesced = (
        object_source(_person(person_id), participation) for person_id in (1, 2, 1)
    )
    assert first == coalesced and first is not coalesced
    admission = _admitted(
        _person_write(1, first),
        _person_write(2, other),
        _person_write(1, coalesced),
        _person_write(1, first),
        meta=_PERSON,
    )
    one, two = admission.composed_writes()
    assert isinstance(one, ObjectLockedWrite) and isinstance(two, ObjectLockedWrite)
    assert [tuple(map(id, write.source_evidence)) for write in (one, two)] == [
        (id(first), id(coalesced)),
        (id(other),),
    ]
    admission.drain_planned()
    assert admission.composed_writes() == ()


def test_discard_forgets_every_source_registration_and_insertion() -> None:
    source = object_source(_person(1))
    admission = _admitted(_person_write(1, source), meta=_PERSON)
    admission.register_read_evidence(source, read_at=0, current=lambda _state, _read_at: False)
    assert admission.resolve_source(source) is SourceRefusal.STALE
    insertion = prepare_wire_write(
        KeyedWriteInstruction("insert", "Person", ({"id": 9, "name": "Ada"},)), _PERSON
    )
    assert isinstance(insertion, PreparedKeyedInstruction)
    _admit(admission, admitted_write(insertion, None))
    ownership = admission.ownership
    endpoint = TemporalRowCoordinates(ENTITY, (1,), OPEN_BITEMPORAL_ENDS)
    admission.complete(WriteEffects(opened=Openings(fresh=(endpoint,))), (), at=1)
    admission.discard()
    assert admission.resolve_source(source) == _person(1)
    assert not admission
    assert admission.insertion_identity(ObjectKey(_PERSON_ENTITY, (("id", 9),))) is None
    assert admission.ownership is ownership
    assert not ownership.owns(endpoint)


class _Untraversable:
    def __iter__(self) -> Iterator[ObjectStateKey]:
        raise AssertionError("completion traversed the settled write's changed states")


def test_completion_publishes_into_the_ownership_planning_borrowed() -> None:
    admission = WriteAdmission(POSITION, inserted_version=_unversioned, observations={})
    ownership = admission.ownership
    _admit(admission, observed_write("amendUntil", START, acctNum="B"))
    admission.drain_planned()
    opening = AllocatedOpening(ENTITY, OPEN_BITEMPORAL_ENDS)
    admission.complete(
        WriteEffects(changed=_Untraversable(), opened=Openings(allocated=(opening,))),
        (42,),
        at=1,
    )
    assert admission.ownership is ownership
    assert ownership.owns(TemporalRowCoordinates(ENTITY, (42,), OPEN_BITEMPORAL_ENDS))


def test_a_completed_version_advance_scopes_the_next_write_its_insertion_authorizes() -> None:
    advanced: list[int | None] = []

    def inserted_version(entity: EntityIdentity, advanced_from: int | None) -> int | None:
        del entity
        advanced.append(advanced_from)
        return 1 if advanced_from is None else advanced_from + 1

    admission = WriteAdmission(_ACCOUNT, inserted_version=inserted_version, observations={})
    _admit(admission, _account_insert(9))
    admission.drain_planned()
    identity = admission.insertion_identity(_account(9))
    assert identity is not None
    _admit(admission, InsertionAuthorizedWrite(_account_amend(9), identity))
    (before,) = admission.composed_writes()
    admission.drain_planned()
    admission.complete(WriteEffects(advanced=(VersionedObjectStateKey(_account(9), 1),)), (), at=1)
    _admit(admission, InsertionAuthorizedWrite(_account_amend(9), identity))
    (after,) = admission.composed_writes()
    assert isinstance(before, InsertionAuthorizedWrite) and isinstance(
        after, InsertionAuthorizedWrite
    )
    assert (before.scope, after.scope) == (
        VersionedObjectStateKey(_account(9), 1),
        VersionedObjectStateKey(_account(9), 2),
    )
    # Completion asks once for the version its update produced, and the later
    # write once for the version it claims.
    assert advanced == [None, 1, 1]


def _stored_insertion_across_two_rows() -> WriteAdmission:
    admission = WriteAdmission(POSITION, inserted_version=_unversioned, observations={})
    _admit(admission, _position_insert())
    admission.drain_planned()
    split = TemporalRowCoordinates(ENTITY, (1,), (Finite(instant=JUN), PLANNED_INFINITY))
    tail = TemporalRowCoordinates(ENTITY, (1,), OPEN_BITEMPORAL_ENDS)
    admission.complete(WriteEffects(opened=Openings(continued=(split, tail))), (), at=1)
    return admission


def _position_insert() -> AdmittedWrite:
    prepared = prepare_wire_write(
        KeyedWriteInstruction(
            "insert", "Position", ({"id": 1, "acctNum": "A", "value": "1.00"},), FEB
        ),
        POSITION,
    )
    assert isinstance(prepared, PreparedKeyedInstruction)
    return admitted_write(prepared, None)


@pytest.mark.parametrize("earlier", [True, False], ids=["both-rows", "later-only"])
def test_a_composed_removal_reaches_the_whole_insertion_only_with_every_row(
    earlier: bool,
) -> None:
    # The later rectangle is destroyed first and the earlier one after it;
    # only both together remove what the insertion opened, so only then does
    # its next insertion follow the removal.
    admission = _stored_insertion_across_two_rows()
    later = retained(rectangle(JUN, INFINITY, "1.00", tx_start=_INSERTED_AT))
    earlier_rectangle = retained(rectangle(FEB, JUN, "1.00", tx_start=_INSERTED_AT))
    _admit(admission, observed_write("terminate", later, valid_from=JUN, until=None))
    if earlier:
        _admit(
            admission,
            observed_write("terminateUntil", earlier_rectangle, valid_from=FEB, until=JUN),
        )
    _admit(admission, _position_insert())
    reinsertion = admission.composed_writes()[-1]
    assert isinstance(reinsertion, PostRemovalInsert) is earlier


# --------------------------------------------------------------------------- #
# A temporal object's target writes meet every other write of it.   #
# --------------------------------------------------------------------------- #
def test_a_restated_caller_condition_is_kept_once_however_often_it_is_overwritten() -> None:
    admission = _admitted(addressed_write(value="1.00"))
    for value in ("2.00", "3.00"):
        _admit(
            admission,
            addressed_write(value=value),
            addressed_write(replaces=True, acctNum="Z", value=value),
        )
    (composed,) = admission.composed_writes()
    assert isinstance(composed, ComposedTemporalWrite)
    assert [contribution.condition for contribution in composed.contributions] == [
        ExpectedTxStart(T0)
    ]
    (segment,) = composed.transform.segments
    assert segment.replaces
    assert dict(segment.assigned or {}) == {"acctNum": "Z", "value": Decimal("3.00")}


def test_an_observed_write_after_a_target_must_state_its_window_and_start() -> None:
    admission = _admitted(addressed_write(value="150.00"))
    _refused(admission, observed_write("amendUntil", START, until=JUN, value="1.00"))
    _refused(admission, observed_write("amendUntil", RESTATED, value="1.00"))
    _admit(admission, observed_write("amendUntil", START, value="1.00"))


def test_a_target_meeting_any_earlier_unequal_contribution_is_refused() -> None:
    # Pure observed writes compose over unequal windows; a target joining them
    # must agree with every one, not only the latest.
    earlier = _admitted(
        observed_write("amend", START, valid_from=JAN, until=None, value="1.00"),
        observed_write("amendUntil", START, value="2.00"),
    )
    _refused(earlier, addressed_write(value="3.00"))
    target_first = _admitted(
        addressed_write(value="3.00"), observed_write("amendUntil", START, value="2.00")
    )
    _refused(target_first, observed_write("amend", START, valid_from=JAN, until=None, value="1.00"))


def test_a_write_disjoint_from_the_latest_but_overlapping_an_earlier_one_is_refused() -> None:
    admission = _admitted(
        observed_write("amendUntil", WHOLE, valid_from=MAR, until=JUN, acctNum="A1"),
        observed_write("amendUntil", WHOLE, valid_from=APR, until=AUG, acctNum="A2"),
        addressed_write(valid_from=SEP, until=OCT, value="150.00"),
    )
    _refused(admission, addressed_write(valid_from=JUL, until=SEP, value="1.00"))
    _refused(admission, observed_write("terminateUntil", WHOLE, valid_from=MAY, until=SEP))


@pytest.mark.parametrize("order", ["observed-first", "target-first"])
def test_a_target_starting_inside_an_observed_rectangle_must_state_its_revision(
    order: str,
) -> None:
    for tx_start, admitted in ((T0, True), (T1, False)):
        observed = observed_write("amendUntil", WHOLE, valid_from=FEB, until=APR, acctNum="O")
        target = addressed_write(valid_from=JUN, until=AUG, tx_start=tx_start, value="150.00")
        held, arriving = (observed, target) if order == "observed-first" else (target, observed)
        admission = _admitted(held)
        if admitted:
            _admit(admission, arriving)
        else:
            _refused(admission, arriving)


def test_a_shared_token_names_whatever_rectangle_holds_each_start() -> None:
    # The source observed only [January, June); a caller stating the same
    # Transaction-Time start for September names whichever rectangle holds it.
    for tx_start in (T0, T1):
        _admitted(
            observed_write("amendUntil", START, valid_from=FEB, until=APR, acctNum="O"),
            addressed_write(valid_from=SEP, until=OCT, tx_start=tx_start, value="1.00"),
        )


def test_a_write_an_insertion_authorized_never_shares_a_targets_window() -> None:
    # An insertion's write states no starting revision a caller's could agree
    # with, so the two cannot be one operation over one window.
    insertion = prepare_wire_write(
        KeyedWriteInstruction(
            "insert", "Position", ({"id": 1, "acctNum": "A", "value": "1.00"},), MAR
        ),
        POSITION,
    )
    amendment = prepare_wire_write(
        KeyedWriteInstruction("amendUntil", "Position", ({"id": 1, "value": "2.00"},), MAR, SEP),
        POSITION,
    )
    assert isinstance(insertion, PreparedKeyedInstruction)
    assert isinstance(amendment, PreparedKeyedInstruction)
    admission = _admitted(addressed_write(value="150.00"), admitted_write(insertion, None))
    identity = admission.insertion_identity(OBJECT)
    assert identity is not None
    _refused(admission, InsertionAuthorizedWrite(amendment, identity))


def test_a_target_beside_writes_of_other_states_of_its_object_is_refused() -> None:
    several = _admitted(_account_observed(1, 2), _account_observed(1, 3), meta=_ACCOUNT)
    _refused(several, _account_target(1, 3))
    other = _admitted(_account_target(1, 3), meta=_ACCOUNT)
    _refused(other, _account_observed(1, 4))
    _refused(other, _account_target(1, 4))
