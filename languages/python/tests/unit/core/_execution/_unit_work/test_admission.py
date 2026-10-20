"""Write admission (`m-unit-work` "Observed-State Coalescing"), observed at the
owner's interface where the write verbs cannot say it precisely: when a
caller-addressed write's confirmation is consulted, how a planned batch drains into the
live ownership, and the window rules a temporal object's caller-addressed
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
from parallax.core import predicate as predicate_algebra
from parallax.core._execution._unit_work.admission import BufferOutcome, WriteAdmission
from parallax.core._execution._unit_work.instructions import (
    ExpectedTxStart,
    PreparedKeyedWrite,
    PreparedPredicateWrite,
    prepare_wire_write,
)
from parallax.core._execution._unit_work.retain import RetainedTargetState
from parallax.core._execution._unit_work.write_items import (
    AfterRemoval,
    BufferItem,
    ChainedTemporalWrite,
    ComposedTemporalWrite,
    InsertionKeyedWrite,
    TargetKeyedWrite,
    target_write,
)
from parallax.core.base import INFINITY
from parallax.core.entity._model import model_of
from parallax.core.metamodel import EntityIdentity, Metamodel
from parallax.core.unit_work import (
    KeyedWriteInstruction,
    PredicateSelection,
    PredicateWriteInstruction,
    RetainedObservation,
    TargetWriteInstruction,
    WriteAssignment,
    WriteEvidenceError,
    buffered_write,
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
    OwnedEndpoint,
    UnitEffects,
)
from parallax.core.write_plan.steps import INFINITY as PLANNED_INFINITY
from parallax.core.write_plan.steps import Finite
from tests._support.planner_probes import RecordingSource
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


def _confirmed(item: TargetKeyedWrite) -> TargetKeyedWrite:
    return item


def _unversioned(entity: EntityIdentity, advanced_from: int | None) -> int | None:
    del entity, advanced_from
    return None


def _admitted(*writes: BufferItem, meta: Metamodel = POSITION) -> WriteAdmission:
    admission = WriteAdmission(meta, inserted_version=_unversioned)
    for write in writes:
        admission.admit(write, confirm_target=_confirmed)
    return admission


def _admit(admission: WriteAdmission, *writes: BufferItem) -> None:
    for write in writes:
        admission.admit(write, confirm_target=_confirmed)


def _refused(admission: WriteAdmission, write: BufferItem) -> None:
    with pytest.raises(WriteEvidenceError) as refusal:
        admission.admit(write, confirm_target=_confirmed)
    assert refusal.value.code == "write-evidence-already-claimed"


def _account(account_id: int) -> ObjectKey:
    return ObjectKey(_ACCOUNT_ENTITY, (("id", account_id),))


def _account_observed(account_id: int, version: int) -> BufferItem:
    prepared = prepare_wire_write(
        KeyedWriteInstruction("amend", "Account", ({"id": account_id, "owner": "Bo"},)), _ACCOUNT
    )
    assert isinstance(prepared, PreparedKeyedWrite)
    state = VersionedObjectStateKey(_account(account_id), version)
    return buffered_write(prepared, RetainedObservation(state, VersionObservation(version), None))


def _account_target(account_id: int, version: int) -> TargetKeyedWrite:
    prepared = prepare_wire_write(
        TargetWriteInstruction(
            "amend", "Account", {"id": account_id, "balance": "1.00"}, if_version=version
        ),
        _ACCOUNT,
    )
    return target_write(prepared, inheritance.view(_ACCOUNT))


def _account_insert(account_id: int) -> PreparedKeyedWrite:
    prepared = prepare_wire_write(
        KeyedWriteInstruction(
            "insert", "Account", ({"id": account_id, "owner": "N", "balance": "5.00"},)
        ),
        _ACCOUNT,
    )
    assert isinstance(prepared, PreparedKeyedWrite)
    return prepared


def _account_amend(account_id: int) -> PreparedKeyedWrite:
    prepared = prepare_wire_write(
        KeyedWriteInstruction("amend", "Account", ({"id": account_id, "owner": "Cy"},)), _ACCOUNT
    )
    assert isinstance(prepared, PreparedKeyedWrite)
    return prepared


def _barrier() -> PreparedPredicateWrite:
    prepared = prepare_wire_write(
        PredicateWriteInstruction(
            "amend",
            PredicateSelection(
                "Wallet",
                predicate_algebra.Comparison("eq", predicate_algebra.FieldSubject("Wallet.id"), 1),
            ),
            assignments=(WriteAssignment("Wallet.owner", "Q"),),
        ),
        _WALLET,
    )
    assert isinstance(prepared, PreparedPredicateWrite)
    return prepared


# --------------------------------------------------------------------------- #
# A caller-addressed write is confirmed once acceptance leaves it unproven.   #
# --------------------------------------------------------------------------- #
class _Confirmations:
    def __init__(self) -> None:
        self.asked: list[TargetKeyedWrite] = []

    def __call__(self, item: TargetKeyedWrite) -> TargetKeyedWrite:
        self.asked.append(item)
        return item


def test_a_pending_write_of_the_targets_state_proves_it_before_confirmation_is_asked() -> None:
    confirm = _Confirmations()
    admission = WriteAdmission(POSITION, inserted_version=_unversioned)
    first = addressed_write(value="150.00")
    admission.admit(first, confirm_target=confirm)
    # A second write over exactly that window starts from the state the first
    # does; one refused for another stated start is never confirmed.
    admission.admit(addressed_write(value="175.00"), confirm_target=confirm)
    with pytest.raises(WriteEvidenceError):
        admission.admit(addressed_write(tx_start=T1, value="1.00"), confirm_target=confirm)
    assert confirm.asked == [first]

    versioned = WriteAdmission(_ACCOUNT, inserted_version=_unversioned)
    versioned.admit(_account_observed(1, 3), confirm_target=confirm)
    versioned.admit(_account_target(1, 3), confirm_target=confirm)
    alone = _account_target(2, 3)
    versioned.admit(alone, confirm_target=confirm)
    assert confirm.asked == [first, alone]


def test_an_inserted_objects_target_is_refused_before_its_conflicts_or_confirmation() -> None:
    confirm = _Confirmations()
    admission = WriteAdmission(_ACCOUNT, inserted_version=lambda _entity, _from: 1)
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

    def retaining(item: TargetKeyedWrite) -> TargetKeyedWrite:
        return dataclasses.replace(item, retained=held)

    admission = WriteAdmission(POSITION, inserted_version=_unversioned)
    admission.admit(addressed_write(value="150.00"), confirm_target=retaining)
    (composed,) = admission.composed_writes()
    assert isinstance(composed, TargetKeyedWrite)
    assert composed.retained is held


# --------------------------------------------------------------------------- #
# A planned batch drains into the live ownership; discard spends nothing.     #
# --------------------------------------------------------------------------- #
def test_a_batch_composition_left_nothing_of_still_needs_its_flush() -> None:
    admission = WriteAdmission(_ACCOUNT, inserted_version=_unversioned)
    assert not admission
    _admit(admission, _account_insert(9))
    deletion = prepare_wire_write(
        KeyedWriteInstruction("delete", "Account", ({"id": 9},)), _ACCOUNT
    )
    outcome = admission.admit(deletion, confirm_target=_confirmed)
    assert outcome is BufferOutcome.CANCELLED_PENDING_INSERT
    assert admission
    assert admission.composed_writes() == ()
    assert admission.drain_planned() == []
    assert not admission


def _person_write(person_id: int, source: RecordingSource) -> BufferItem:
    prepared = prepare_wire_write(
        KeyedWriteInstruction("amend", "Person", ({"id": person_id, "name": "Grace"},)), _PERSON
    )
    assert isinstance(prepared, PreparedKeyedWrite)
    return buffered_write(prepared, ObjectKey(_PERSON_ENTITY, (("id", person_id),)), source=source)


def test_drain_hands_over_every_object_source_in_admission_order_and_starts_afresh() -> None:
    first, other, coalesced = RecordingSource(), RecordingSource(), RecordingSource()
    admission = _admitted(
        _person_write(1, first),
        _person_write(2, other),
        _person_write(1, coalesced),
        _person_write(1, first),
        meta=_PERSON,
    )
    sources = admission.drain_planned()
    assert list(sources) == [first, other, coalesced, first]
    assert not any((first.consumed, other.consumed, coalesced.consumed))
    later = RecordingSource()
    _admit(admission, _person_write(1, later))
    assert list(sources) == [first, other, coalesced, first]
    assert list(admission.drain_planned()) == [later]


def test_discard_leaves_pending_authority_unspent_and_forgets_every_insertion() -> None:
    source = RecordingSource()
    admission = _admitted(_person_write(1, source), meta=_PERSON)
    insertion = prepare_wire_write(
        KeyedWriteInstruction("insert", "Person", ({"id": 9, "name": "Ada"},)), _PERSON
    )
    assert isinstance(insertion, PreparedKeyedWrite)
    _admit(admission, insertion)
    ownership = admission.ownership
    endpoint = OwnedEndpoint(ENTITY, (1,), OPEN_BITEMPORAL_ENDS)
    admission.complete_unit(UnitEffects(opened=Openings(fresh=(endpoint,))), ())
    admission.discard()
    assert not source.consumed
    assert not admission
    assert admission.drain_planned() == []
    assert admission.insertion_identity(ObjectKey(_PERSON_ENTITY, (("id", 9),))) is None
    assert admission.ownership is ownership
    assert not ownership.owns(endpoint)


class _Untraversable:
    def __iter__(self) -> Iterator[ObjectStateKey]:
        raise AssertionError("completion traversed the unit's changed states")


def test_completion_publishes_into_the_ownership_planning_borrowed() -> None:
    admission = WriteAdmission(POSITION, inserted_version=_unversioned)
    ownership = admission.ownership
    _admit(admission, observed_write("amendUntil", START, acctNum="B"))
    admission.drain_planned()
    opening = AllocatedOpening(ENTITY, OPEN_BITEMPORAL_ENDS)
    admission.complete_unit(
        UnitEffects(changed=_Untraversable(), opened=Openings(allocated=(opening,))), (42,)
    )
    assert admission.ownership is ownership
    assert ownership.owns(OwnedEndpoint(ENTITY, (42,), OPEN_BITEMPORAL_ENDS))


def test_a_completed_version_advance_scopes_the_next_write_its_insertion_authorizes() -> None:
    advanced: list[int | None] = []

    def inserted_version(entity: EntityIdentity, advanced_from: int | None) -> int | None:
        del entity
        advanced.append(advanced_from)
        return 1 if advanced_from is None else advanced_from + 1

    admission = WriteAdmission(_ACCOUNT, inserted_version=inserted_version)
    _admit(admission, _account_insert(9))
    admission.drain_planned()
    identity = admission.insertion_identity(_account(9))
    assert identity is not None
    _admit(admission, InsertionKeyedWrite(_account_amend(9), identity))
    (before,) = admission.composed_writes()
    admission.drain_planned()
    admission.record_version_advance(VersionedObjectStateKey(_account(9), 1))
    _admit(admission, InsertionKeyedWrite(_account_amend(9), identity))
    (after,) = admission.composed_writes()
    assert isinstance(before, InsertionKeyedWrite) and isinstance(after, InsertionKeyedWrite)
    assert (before.scope, after.scope) == (
        VersionedObjectStateKey(_account(9), 1),
        VersionedObjectStateKey(_account(9), 2),
    )
    assert advanced == [None, 1]


def _stored_insertion_across_two_rows() -> WriteAdmission:
    admission = WriteAdmission(POSITION, inserted_version=_unversioned)
    _admit(admission, _position_insert())
    admission.drain_planned()
    split = OwnedEndpoint(ENTITY, (1,), (Finite(instant=JUN), PLANNED_INFINITY))
    tail = OwnedEndpoint(ENTITY, (1,), OPEN_BITEMPORAL_ENDS)
    admission.complete_unit(UnitEffects(opened=Openings(continued=(split, tail))), ())
    return admission


def _position_insert() -> PreparedKeyedWrite:
    prepared = prepare_wire_write(
        KeyedWriteInstruction(
            "insert", "Position", ({"id": 1, "acctNum": "A", "value": "1.00"},), FEB
        ),
        POSITION,
    )
    assert isinstance(prepared, PreparedKeyedWrite)
    return prepared


@pytest.mark.parametrize("earlier_region", [True, False], ids=["both-regions", "later-only"])
def test_a_removal_split_by_a_barrier_reaches_the_whole_insertion_in_start_order(
    earlier_region: bool,
) -> None:
    # The later rectangle is destroyed before the barrier and the earlier one
    # after it; only both together remove what the insertion opened, so only
    # then does its next insertion follow the removal.
    admission = _stored_insertion_across_two_rows()
    later = retained(rectangle(JUN, INFINITY, "1.00", tx_start=_INSERTED_AT))
    earlier = retained(rectangle(FEB, JUN, "1.00", tx_start=_INSERTED_AT))
    _admit(admission, observed_write("terminate", later, valid_from=JUN, until=None), _barrier())
    if earlier_region:
        _admit(admission, observed_write("terminateUntil", earlier, valid_from=FEB, until=JUN))
    _admit(admission, _position_insert())
    reinsertion = admission.composed_writes()[-1]
    assert isinstance(reinsertion, AfterRemoval) is earlier_region


# --------------------------------------------------------------------------- #
# A temporal object's caller-addressed writes meet every other write of it.   #
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


def test_admission_across_a_barrier_judges_every_write_of_the_object() -> None:
    admission = _admitted(addressed_write(valid_from=FEB, until=APR, value="1.00"), _barrier())
    _refused(admission, observed_write("amendUntil", WHOLE, valid_from=MAR, until=JUN, acctNum="O"))
    # One window and one start compose, though they execute as two units.
    _admit(admission, observed_write("amendUntil", WHOLE, valid_from=FEB, until=APR, acctNum="O"))
    first, _barrier_write, second = admission.composed_writes()
    assert isinstance(first, ChainedTemporalWrite) and first.leads
    assert isinstance(second, ChainedTemporalWrite) and second.follows


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
    assert isinstance(insertion, PreparedKeyedWrite)
    assert isinstance(amendment, PreparedKeyedWrite)
    admission = _admitted(addressed_write(value="150.00"), insertion)
    identity = admission.insertion_identity(OBJECT)
    assert identity is not None
    _refused(admission, InsertionKeyedWrite(amendment, identity))


def test_a_target_beside_writes_of_other_states_of_its_object_is_refused() -> None:
    several = _admitted(_account_observed(1, 2), _account_observed(1, 3), meta=_ACCOUNT)
    _refused(several, _account_target(1, 3))
    other = _admitted(_account_target(1, 3), meta=_ACCOUNT)
    _refused(other, _account_observed(1, 4))
    _refused(other, _account_target(1, 4))
