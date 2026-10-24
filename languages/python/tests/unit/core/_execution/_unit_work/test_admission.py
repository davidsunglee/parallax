"""Write admission (`m-unit-work` "Observed-State Coalescing"), observed at the
owner's interface where the write verbs cannot say it precisely: when a
target write's confirmation is consulted, how a planned buffer drains into the
insertions its source authority keeps, and the window rules a temporal
object's target writes meet that the verb matrices do not reach. What a caller sees through
the verbs is the snapshot and API suites'."""

from __future__ import annotations

import dataclasses
import datetime as dt
from collections.abc import Callable
from decimal import Decimal

import pytest

from parallax.conformance.class_models import MODELS as CLASS_MODELS
from parallax.core import inheritance, temporal_read
from parallax.core._execution._unit_work.admission import BufferOutcome, WriteAdmission
from parallax.core._execution._unit_work.claims import WriteIntent
from parallax.core._execution._unit_work.instructions import (
    ExpectedTxStart,
    PreparedKeyedInstruction,
    prepare_wire_write,
)
from parallax.core._execution._unit_work.retain import (
    NO_INSERTION_AUTHORITY,
    InsertionIdentity,
    KeyedWriteRefusalAdvice,
    ParticipationToken,
    ReadEvidence,
    RetainedTargetState,
)
from parallax.core._execution._unit_work.source_authority import SourceAuthority
from parallax.core._execution._unit_work.write_items import (
    AdmittedWrite,
    ComposedBitemporalOpening,
    ComposedTemporalWrite,
    InsertionAuthorizedIntent,
    InsertionAuthorizedWrite,
    KeyedInsert,
    ObjectLockedWrite,
    PostRemovalInsert,
    StateObservedIntent,
    StateObservedWrite,
    TargetIntent,
    TargetWrite,
    TemporalCoverageWrite,
    target_write,
)
from parallax.core.base import INFINITY
from parallax.core.entity._model import model_of
from parallax.core.execution import KeyedWriteValueError
from parallax.core.metamodel import EntityIdentity, Metamodel
from parallax.core.temporal_read import TimeInterval
from parallax.core.unit_work import (
    KeyedMutation,
    KeyedWriteInstruction,
    ReadAuthorizedWrite,
    RetainedObservation,
    TargetWriteInstruction,
    WriteEvidenceError,
    admitted_write,
)
from parallax.core.write_plan import (
    ObjectKey,
    PredecessorRow,
    TemporalObservation,
    VersionObservation,
)
from parallax.core.write_plan.keys import (
    TemporalObjectStateKey,
    VersionedObjectStateKey,
)
from parallax.core.write_plan.plan import (
    OPEN_BITEMPORAL_ENDS,
    Openings,
    TemporalRowCoordinates,
    WriteEffects,
)
from parallax.core.write_plan.steps import INFINITY as PLANNED_INFINITY
from parallax.core.write_plan.steps import Finite
from tests._support.planner_probes import admit, object_source, source_authority
from tests.unit._corpus_model_support import corpus_records, formed
from tests.unit.core._execution._unit_work._temporal_targets_support import (
    APR,
    AUG,
    DEC,
    ENTITY,
    FEB,
    JAN,
    JUL,
    JUN,
    LATER,
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
_BALANCE = formed(corpus_records()["balance"])
_BALANCE_OBJECT = ObjectKey(EntityIdentity("parallax.compatibility", "Balance"), (("id", 1),))
_INSERTED_AT = dt.datetime(2024, 1, 10, tzinfo=dt.UTC)


def _confirmed(item: TargetWrite) -> TargetWrite:
    return item


def _unversioned(entity: EntityIdentity, advanced_from: int | None) -> int | None:
    del entity, advanced_from
    return None


def _admitted(
    *writes: AdmittedWrite, meta: Metamodel = POSITION, authority: SourceAuthority | None = None
) -> WriteAdmission:
    admission = WriteAdmission(
        meta,
        authority=source_authority(meta, inserted_version=_unversioned)
        if authority is None
        else authority,
    )
    _admit(admission, *writes)
    return admission


def _admit(admission: WriteAdmission, *writes: AdmittedWrite) -> None:
    for write in writes:
        admit(admission, write)


def _refused(
    admission: WriteAdmission, write: ReadAuthorizedWrite | InsertionAuthorizedWrite | TargetWrite
) -> None:
    with pytest.raises(WriteEvidenceError) as refusal:
        admission.admit(write, confirm_target=_confirmed)
    assert refusal.value.code == "write-evidence-already-claimed"


def _account(account_id: int) -> ObjectKey:
    return ObjectKey(_ACCOUNT_ENTITY, (("id", account_id),))


def _account_observed(account_id: int, version: int) -> ReadAuthorizedWrite:
    prepared = prepare_wire_write(
        KeyedWriteInstruction("amend", "Account", ({"id": account_id, "owner": "Bo"},)), _ACCOUNT
    )
    assert isinstance(prepared, PreparedKeyedInstruction)
    state = VersionedObjectStateKey(_account(account_id), version)
    return admitted_write(
        prepared, RetainedObservation(state, VersionObservation(version), None), state.object
    )


def _account_target(account_id: int, version: int) -> TargetWrite:
    prepared = prepare_wire_write(
        TargetWriteInstruction(
            "amend", "Account", {"id": account_id, "balance": "1.00"}, if_version=version
        ),
        _ACCOUNT,
    )
    return target_write(prepared, inheritance.view(_ACCOUNT))


def _account_insert(account_id: int) -> KeyedInsert:
    prepared = prepare_wire_write(
        KeyedWriteInstruction(
            "insert", "Account", ({"id": account_id, "owner": "N", "balance": "5.00"},)
        ),
        _ACCOUNT,
    )
    assert isinstance(prepared, PreparedKeyedInstruction)
    return admitted_write(prepared, None, _account(account_id))


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
    admission = _admitted()
    first = addressed_write(value="150.00")
    admission.admit(first, confirm_target=confirm)
    # A second write over exactly that window starts from the state the first
    # does; one refused for another stated start is never confirmed.
    admission.admit(addressed_write(value="175.00"), confirm_target=confirm)
    with pytest.raises(WriteEvidenceError):
        admission.admit(addressed_write(tx_start=T1, value="1.00"), confirm_target=confirm)
    assert confirm.asked == [first]

    versioned = _admitted(meta=_ACCOUNT)
    versioned.admit(_account_observed(1, 3), confirm_target=confirm)
    versioned.admit(_account_target(1, 3), confirm_target=confirm)
    alone = _account_target(2, 3)
    versioned.admit(alone, confirm_target=confirm)
    assert confirm.asked == [first, alone]


def test_an_inserted_objects_target_is_refused_before_its_conflicts_or_confirmation() -> None:
    confirm = _Confirmations()
    admission = _admitted(meta=_ACCOUNT)
    admission.admit_insert(_account_insert(1), insertion_advice=None)
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

    admission = _admitted()
    admission.admit(addressed_write(value="150.00"), confirm_target=retaining)
    (composed,) = admission.composed_writes()
    assert isinstance(composed, TargetWrite)
    assert composed.retained is held
    (intent,) = composed.intents
    assert isinstance(intent, TargetIntent)
    assert intent.retained is held


# --------------------------------------------------------------------------- #
# A planned buffer drains its insertions into the source authority.         #
# --------------------------------------------------------------------------- #
def test_a_batch_composition_left_nothing_of_still_needs_its_flush() -> None:
    admission = _admitted(meta=_ACCOUNT)
    assert not admission
    identity = admission.admit_insert(_account_insert(9), insertion_advice=None)
    deletion = prepare_wire_write(
        KeyedWriteInstruction("delete", "Account", ({"id": 9},)), _ACCOUNT
    )
    assert isinstance(deletion, PreparedKeyedInstruction)
    assert identity is not None
    outcome = admission.admit(
        admitted_write(deletion, None, _account(9), authority=identity), confirm_target=_confirmed
    )
    assert outcome is BufferOutcome.CANCELLED_PENDING_INSERT
    assert admission
    assert admission.composed_writes() == ()
    admission.drain_planned()
    assert not admission


def test_an_amendment_folded_into_a_pending_insert_leaves_it_an_insert() -> None:
    admission = _admitted(meta=_ACCOUNT)
    identity = admission.admit_insert(_account_insert(9), insertion_advice=None)
    assert identity is not None
    _admit(admission, admitted_write(_account_amend(9), None, _account(9), authority=identity))
    (insert,) = admission.composed_writes()
    assert isinstance(insert, KeyedInsert)
    assert insert.instruction.mutation == "insert"
    assert insert.instruction.rows[0]["owner"] == "Cy"


def _person(person_id: int) -> ObjectKey:
    return ObjectKey(_PERSON_ENTITY, (("id", person_id),))


def _person_write(person_id: int, source: ReadEvidence) -> ReadAuthorizedWrite:
    prepared = prepare_wire_write(
        KeyedWriteInstruction("amend", "Person", ({"id": person_id, "name": "Grace"},)), _PERSON
    )
    assert isinstance(prepared, PreparedKeyedInstruction)
    return admitted_write(prepared, _person(person_id), _person(person_id), source=source)


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


def test_discard_drops_the_buffer_and_leaves_the_authoritys_insertions_alone() -> None:
    authority = source_authority(_PERSON, inserted_version=_unversioned)
    admission = _admitted(
        _person_write(1, object_source(_person(1))), meta=_PERSON, authority=authority
    )
    insertion = prepare_wire_write(
        KeyedWriteInstruction("insert", "Person", ({"id": 9, "name": "Ada"},)), _PERSON
    )
    assert isinstance(insertion, PreparedKeyedInstruction)
    identity = admission.admit_insert(
        admitted_write(insertion, None, _person(9)), insertion_advice=None
    )
    assert identity is not None
    admission.discard()
    assert not admission
    assert admission.composed_writes() == ()
    # Clearing the insertions is the authority's own step of an attempt's discard.
    assert authority.insertion_authority(identity) is None


def test_a_completed_version_advance_scopes_the_next_write_its_insertion_authorizes() -> None:
    advanced: list[int | None] = []

    def inserted_version(entity: EntityIdentity, advanced_from: int | None) -> int | None:
        del entity
        advanced.append(advanced_from)
        return 1 if advanced_from is None else advanced_from + 1

    authority = source_authority(_ACCOUNT, inserted_version=inserted_version)
    admission = _admitted(meta=_ACCOUNT, authority=authority)
    identity = admission.admit_insert(_account_insert(9), insertion_advice=None)
    admission.drain_planned()
    assert identity is not None
    _admit(admission, InsertionAuthorizedWrite(_account_amend(9), _account(9), identity))
    (before,) = admission.composed_writes()
    admission.drain_planned()
    authority.complete_write(WriteEffects(advanced=(VersionedObjectStateKey(_account(9), 1),)), ())
    _admit(admission, InsertionAuthorizedWrite(_account_amend(9), _account(9), identity))
    (after,) = admission.composed_writes()
    assert isinstance(before, InsertionAuthorizedWrite) and isinstance(
        after, InsertionAuthorizedWrite
    )
    assert (before.claim_scope, after.claim_scope) == (
        VersionedObjectStateKey(_account(9), 1),
        VersionedObjectStateKey(_account(9), 2),
    )
    # The first write claims the version an insert stores; completion asks
    # once for the version its update produced, which the later write reuses.
    assert advanced == [None, 1]


def _stored_insertion_across_two_rows() -> WriteAdmission:
    authority = source_authority(POSITION, inserted_version=_unversioned)
    admission = _admitted(_position_insert(), authority=authority)
    admission.drain_planned()
    split = TemporalRowCoordinates(ENTITY, (1,), (Finite(instant=JUN), PLANNED_INFINITY))
    tail = TemporalRowCoordinates(ENTITY, (1,), OPEN_BITEMPORAL_ENDS)
    authority.complete_write(WriteEffects(opened=Openings(continued=(split, tail))), ())
    return admission


def _position_insert() -> KeyedInsert:
    prepared = prepare_wire_write(
        KeyedWriteInstruction(
            "insert", "Position", ({"id": 1, "acctNum": "A", "value": "1.00"},), FEB
        ),
        POSITION,
    )
    assert isinstance(prepared, PreparedKeyedInstruction)
    return admitted_write(prepared, None, OBJECT)


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
# Buffering an insert refuses a repeat or answers the identity it issued.     #
# --------------------------------------------------------------------------- #
_OPENER = KeyedWriteRefusalAdvice(
    not_stored="not stored", already_stored="already stored", repeated_insert="amend the opener"
)
_REPEATER = KeyedWriteRefusalAdvice(
    not_stored="not stored", already_stored="already stored", repeated_insert="amend the repeat"
)
_POSITION_ROW = TemporalRowCoordinates(ENTITY, (1,), OPEN_BITEMPORAL_ENDS)


@pytest.mark.parametrize(
    ("meta", "insert", "stored_rows"),
    [
        (_ACCOUNT, lambda: _account_insert(9), ()),
        (_BALANCE, lambda: _balance_insert(), ()),
        (POSITION, _position_insert, (_POSITION_ROW,)),
    ],
    ids=["non-temporal", "transaction-time-only", "bitemporal"],
)
def test_a_repeated_insert_is_refused_with_its_openers_advice_and_changes_nothing(
    meta: Metamodel, insert: Callable[[], KeyedInsert], stored_rows: tuple[TemporalRowCoordinates]
) -> None:
    authority = source_authority(meta, inserted_version=_unversioned)
    admission = _admitted(meta=meta, authority=authority)
    identity = admission.admit_insert(insert(), insertion_advice=_OPENER)
    assert identity is not None
    for stored in (False, True):
        if stored:
            # Stored, its coverage still repeats it.
            admission.drain_planned()
            authority.complete_write(WriteEffects(opened=Openings(continued=stored_rows)), ())
        pending = admission.composed_writes()
        with pytest.raises(KeyedWriteValueError) as refusal:
            admission.admit_insert(insert(), insertion_advice=_REPEATER)
        assert refusal.value.code == "write-value-already-stored"
        assert refusal.value.message.endswith("amend the opener")
        assert admission.composed_writes() == pending
        assert authority.insertion_authority(identity) is not NO_INSERTION_AUTHORITY


def _account_delete_through(identity: InsertionIdentity) -> InsertionAuthorizedWrite:
    prepared = prepare_wire_write(
        KeyedWriteInstruction("delete", "Account", ({"id": 9},)), _ACCOUNT
    )
    assert isinstance(prepared, PreparedKeyedInstruction)
    return InsertionAuthorizedWrite(prepared, _account(9), identity)


def _balance_terminate_through(identity: InsertionIdentity) -> InsertionAuthorizedWrite:
    prepared = prepare_wire_write(
        KeyedWriteInstruction("terminate", "Balance", ({"id": 1},)), _BALANCE
    )
    assert isinstance(prepared, PreparedKeyedInstruction)
    return InsertionAuthorizedWrite(prepared, _BALANCE_OBJECT, identity)


@pytest.mark.parametrize(
    ("meta", "insert", "removal"),
    [
        (_ACCOUNT, lambda: _account_insert(9), _account_delete_through),
        (_BALANCE, lambda: _balance_insert(), _balance_terminate_through),
    ],
    ids=["non-temporal", "transaction-time-only"],
)
def test_an_insert_after_a_pending_whole_removal_follows_it_as_a_first_opening(
    meta: Metamodel,
    insert: Callable[[], KeyedInsert],
    removal: Callable[[InsertionIdentity], InsertionAuthorizedWrite],
) -> None:
    authority = source_authority(meta, inserted_version=_unversioned)
    admission = _admitted(meta=meta, authority=authority)
    stored = admission.admit_insert(insert(), insertion_advice=_OPENER)
    assert stored is not None
    admission.drain_planned()
    _admit(admission, removal(stored))
    again = admission.admit_insert(insert(), insertion_advice=_REPEATER)
    assert again is not None and again is not stored
    assert isinstance(admission.composed_writes()[-1], PostRemovalInsert)
    assert authority.insertion_authority(stored) is NO_INSERTION_AUTHORITY
    # Planning stores the reinsertion after the removal it follows, so the
    # removal retires nothing of it, and a further insert repeats it.
    admission.drain_planned()
    assert authority.insertion_authority(again) is None
    with pytest.raises(KeyedWriteValueError, match="amend the repeat"):
        admission.admit_insert(insert(), insertion_advice=None)


def test_a_pending_reinsertion_claims_from_the_version_an_insert_stores() -> None:
    def inserted_version(entity: EntityIdentity, advanced_from: int | None) -> int | None:
        del entity
        return 1 if advanced_from is None else advanced_from + 1

    authority = source_authority(_ACCOUNT, inserted_version=inserted_version)
    admission = _admitted(meta=_ACCOUNT, authority=authority)
    stored = admission.admit_insert(_account_insert(9), insertion_advice=None)
    assert stored is not None
    admission.drain_planned()
    authority.complete_write(WriteEffects(advanced=(VersionedObjectStateKey(_account(9), 1),)), ())
    _admit(admission, _account_delete_through(stored))
    again = admission.admit_insert(_account_insert(9), insertion_advice=None)
    assert again is not None
    (deletion, _reinsertion) = admission.composed_writes()
    assert isinstance(deletion, InsertionAuthorizedWrite)
    assert deletion.claim_scope == VersionedObjectStateKey(_account(9), 2)
    admission.drain_planned()
    _admit(admission, InsertionAuthorizedWrite(_account_amend(9), _account(9), again))
    (amendment,) = admission.composed_writes()
    assert isinstance(amendment, InsertionAuthorizedWrite)
    assert amendment.claim_scope == VersionedObjectStateKey(_account(9), 1)


@pytest.mark.parametrize("flushed", [False, True], ids=["cancelled-pending", "removed-stored"])
def test_an_inserted_objects_target_stays_refused_once_its_insertion_retires(
    flushed: bool,
) -> None:
    authority = source_authority(_ACCOUNT, inserted_version=lambda _entity, _from: 1)
    admission = _admitted(meta=_ACCOUNT, authority=authority)
    identity = admission.admit_insert(_account_insert(9), insertion_advice=None)
    assert identity is not None
    if flushed:
        admission.drain_planned()
    _admit(admission, _account_delete_through(identity))
    admission.drain_planned()
    assert authority.insertion_authority(identity) is NO_INSERTION_AUTHORITY
    with pytest.raises(WriteEvidenceError) as refusal:
        admission.admit(_account_target(9, 1), confirm_target=_confirmed)
    assert refusal.value.code == "write-evidence-inserted"


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
    assert composed.intents == (
        TargetIntent(WriteIntent("assignment", TimeInterval(MAR, SEP)), ExpectedTxStart(T0)),
    )
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
    admission = _admitted(addressed_write(value="150.00"))
    identity = admission.admit_insert(
        admitted_write(insertion, None, OBJECT), insertion_advice=None
    )
    assert identity is not None
    _refused(admission, InsertionAuthorizedWrite(amendment, OBJECT, identity))


# --------------------------------------------------------------------------- #
# Only a write its insertion authorized joins a pending Bitemporal opening.   #
# --------------------------------------------------------------------------- #
def _position(
    mutation: KeyedMutation, valid_from: dt.datetime, until: dt.datetime | None, **members: object
) -> PreparedKeyedInstruction:
    prepared = prepare_wire_write(
        KeyedWriteInstruction(mutation, "Position", ({"id": 1, **members},), valid_from, until),
        POSITION,
    )
    assert isinstance(prepared, PreparedKeyedInstruction)
    return prepared


def _pending_august_opening() -> tuple[
    WriteAdmission, SourceAuthority, KeyedInsert, InsertionIdentity
]:
    """An admission holding a pending insertion of Position 1 over
    [August, December), disjoint from the stored [January, June) a read
    observed, its source authority, and the identity buffering it issued."""
    insert = admitted_write(
        _position("insertUntil", AUG, DEC, acctNum="N", value="300.00"), None, OBJECT
    )
    authority = source_authority(POSITION, inserted_version=_unversioned)
    admission = _admitted(authority=authority)
    identity = admission.admit_insert(insert, insertion_advice=None)
    assert identity is not None
    return admission, authority, insert, identity


def _read_authorized(mutation: KeyedMutation, source: ReadEvidence) -> ReadAuthorizedWrite:
    members: dict[str, object] = {"value": "150.00"} if mutation == "amendUntil" else {}
    return admitted_write(_position(mutation, MAR, MAY, **members), START, OBJECT, source=source)


@pytest.mark.parametrize("mutation", ["amendUntil", "terminateUntil"])
def test_a_read_authorized_bitemporal_write_stays_apart_from_a_pending_opening(
    mutation: KeyedMutation,
) -> None:
    admission, _authority, insert, _identity = _pending_august_opening()
    source = ReadEvidence(ENTITY, OBJECT, ParticipationToken(), START)
    outcome = admission.admit(_read_authorized(mutation, source), confirm_target=_confirmed)
    assert outcome is BufferOutcome.BUFFERED
    opening, stored = admission.composed_writes()
    # The insertion's own coverage is untouched, and the read's change keeps
    # its own evidence as a write against the coverage that read observed.
    assert opening is insert
    assert not isinstance(stored, KeyedInsert | ComposedBitemporalOpening | PostRemovalInsert)
    assert (stored.phase, stored.object_key) == (
        "update" if mutation == "amendUntil" else "delete",
        OBJECT,
    )
    assert tuple(map(id, stored.source_evidence)) == (id(source),)


def _through_the_insertion(
    admission: WriteAdmission,
    identity: InsertionIdentity,
    mutation: KeyedMutation,
    until: dt.datetime | None,
    **members: object,
) -> BufferOutcome:
    write = admitted_write(
        _position(mutation, AUG, until, **members), None, OBJECT, authority=identity
    )
    return admission.admit(write, confirm_target=_confirmed)


def test_a_write_through_the_insertion_still_composes_with_its_opening_beside_a_read() -> None:
    admission, _authority, insert, identity = _pending_august_opening()
    source = ReadEvidence(ENTITY, OBJECT, ParticipationToken(), START)
    _admit(admission, _read_authorized("amendUntil", source))
    _through_the_insertion(admission, identity, "amendUntil", SEP, value="350.00")
    opening, stored = admission.composed_writes()
    assert isinstance(opening, ComposedBitemporalOpening)
    assert opening.insert is insert
    assert opening.intents == (WriteIntent("assignment", TimeInterval(AUG, SEP)),)
    assert not isinstance(stored, PostRemovalInsert)
    assert tuple(map(id, stored.source_evidence)) == (id(source),)


def test_cancelling_an_opening_leaves_a_read_authorized_write_beside_it_standing() -> None:
    admission, authority, _insert, identity = _pending_august_opening()
    source = ReadEvidence(ENTITY, OBJECT, ParticipationToken(), START)
    _admit(admission, _read_authorized("amendUntil", source))
    (_opening, stored) = admission.composed_writes()
    outcome = _through_the_insertion(admission, identity, "terminate", None)
    assert outcome is BufferOutcome.CANCELLED_PENDING_INSERT
    assert admission.composed_writes() == (stored,)
    assert authority.insertion_authority(identity) is NO_INSERTION_AUTHORITY


def _balance_insert() -> KeyedInsert:
    prepared = prepare_wire_write(
        KeyedWriteInstruction("insert", "Balance", ({"id": 1, "acctNum": "N", "value": "5.00"},)),
        _BALANCE,
    )
    assert isinstance(prepared, PreparedKeyedInstruction)
    return admitted_write(prepared, None, _BALANCE_OBJECT)


def _balance_observed(mutation: KeyedMutation) -> ReadAuthorizedWrite:
    members: dict[str, object] = {"value": "7.00"} if mutation == "amend" else {}
    prepared = prepare_wire_write(
        KeyedWriteInstruction(mutation, "Balance", ({"id": 1, **members},)), _BALANCE
    )
    assert isinstance(prepared, PreparedKeyedInstruction)
    row = PredecessorRow(
        members={
            "id": 1,
            "acctNum": "A",
            "value": Decimal("1.00"),
            "txStart": T0,
            "txEnd": INFINITY,
        }
    )
    shape = temporal_read.view(_BALANCE).shape(_BALANCE_OBJECT.entity)
    assert shape is not None
    state = TemporalObjectStateKey(_BALANCE_OBJECT, temporal_read.milestone_edge(shape, row, None))
    observation = RetainedObservation(state, TemporalObservation(predecessor=row), None)
    return admitted_write(
        prepared,
        observation,
        _BALANCE_OBJECT,
        source=ReadEvidence(
            _BALANCE_OBJECT.entity, _BALANCE_OBJECT, ParticipationToken(), observation
        ),
    )


def _account_observed_delete(account_id: int, version: int) -> ReadAuthorizedWrite:
    prepared = prepare_wire_write(
        KeyedWriteInstruction("delete", "Account", ({"id": account_id},)), _ACCOUNT
    )
    assert isinstance(prepared, PreparedKeyedInstruction)
    state = VersionedObjectStateKey(_account(account_id), version)
    return admitted_write(
        prepared, RetainedObservation(state, VersionObservation(version), None), state.object
    )


@pytest.mark.parametrize(
    ("meta", "insert", "amendment", "member", "value"),
    [
        (_ACCOUNT, lambda: _account_insert(9), lambda: _account_observed(9, 3), "owner", "Bo"),
        (
            _BALANCE,
            _balance_insert,
            lambda: _balance_observed("amend"),
            "value",
            Decimal("7.00"),
        ),
    ],
    ids=["non-temporal", "transaction-time-only"],
)
def test_a_read_authorized_amendment_still_folds_into_an_ordinary_pending_insert(
    meta: Metamodel,
    insert: Callable[[], KeyedInsert],
    amendment: Callable[[], ReadAuthorizedWrite],
    member: str,
    value: object,
) -> None:
    (folded,) = _admitted(insert(), amendment(), meta=meta).composed_writes()
    assert isinstance(folded, KeyedInsert)
    assert folded.instruction.mutation == "insert"
    assert folded.instruction.rows[0][member] == value
    assert folded.source_evidence == ()


@pytest.mark.parametrize(
    ("meta", "insert", "destruction"),
    [
        (_ACCOUNT, lambda: _account_insert(9), lambda: _account_observed_delete(9, 3)),
        (_BALANCE, _balance_insert, lambda: _balance_observed("terminate")),
    ],
    ids=["non-temporal", "transaction-time-only"],
)
def test_a_read_authorized_destruction_still_cancels_an_ordinary_pending_insert(
    meta: Metamodel,
    insert: Callable[[], KeyedInsert],
    destruction: Callable[[], ReadAuthorizedWrite],
) -> None:
    admission = _admitted(insert(), meta=meta)
    outcome = admission.admit(destruction(), confirm_target=_confirmed)
    assert outcome is BufferOutcome.CANCELLED_PENDING_INSERT
    assert admission.composed_writes() == ()


def test_a_target_beside_writes_of_other_states_of_its_object_is_refused() -> None:
    several = _admitted(_account_observed(1, 2), _account_observed(1, 3), meta=_ACCOUNT)
    _refused(several, _account_target(1, 3))
    other = _admitted(_account_target(1, 3), meta=_ACCOUNT)
    _refused(other, _account_observed(1, 4))
    _refused(other, _account_target(1, 4))


# --------------------------------------------------------------------------- #
# A temporal object's writes compose from the first; an initial observed run   #
# of one observation over one window keeps one intent.                         #
# --------------------------------------------------------------------------- #
def _sourced(
    mutation: KeyedMutation,
    evidence: RetainedObservation,
    source: ReadEvidence,
    *,
    valid_from: dt.datetime = MAR,
    until: dt.datetime | None = SEP,
    **members: object,
) -> ReadAuthorizedWrite:
    write = observed_write(mutation, evidence, valid_from=valid_from, until=until, **members)
    return admitted_write(write.instruction, evidence, write.object_key, source=source)


_PARTICIPATION = ParticipationToken()


def _evidence(observation: RetainedObservation) -> ReadEvidence:
    return ReadEvidence(ENTITY, OBJECT, _PARTICIPATION, observation)


def _composition(admission: WriteAdmission) -> TemporalCoverageWrite:
    """Position 1's pending writes against its stored coverage: one alone, or
    their composition."""
    (pending,) = (
        write
        for write in admission.composed_writes()
        if isinstance(
            write,
            StateObservedWrite | InsertionAuthorizedWrite | TargetWrite | ComposedTemporalWrite,
        )
        and write.object_key == OBJECT
    )
    return pending


def _observed_intents(composed: TemporalCoverageWrite) -> list[StateObservedIntent]:
    intents = [intent for intent in composed.intents if isinstance(intent, StateObservedIntent)]
    assert len(intents) == len(composed.intents)
    return intents


def test_a_first_observed_write_stays_alone_and_answers_its_one_intent() -> None:
    source = _evidence(START)
    write = _sourced("amendUntil", START, source, value="150.00")
    admission = _admitted(write)
    composed = _composition(admission)
    assert composed is write
    assert composed.object_key == OBJECT
    (intent,) = _observed_intents(composed)
    assert intent.intent == WriteIntent("assignment", TimeInterval(MAR, SEP))
    assert intent.retained_observation is START
    assert len(intent.source_evidence) == 1 and intent.source_evidence[0] is source
    (segment,) = composed.transform.segments
    assert dict(segment.assigned or {}) == {"value": Decimal("150.00")}


def test_a_first_target_write_stays_alone_and_answers_its_caller_condition() -> None:
    composed = _composition(_admitted(addressed_write(until=None, value="150.00")))
    assert isinstance(composed, TargetWrite)
    assert composed.intents == (
        TargetIntent(WriteIntent("assignment", TimeInterval(MAR, INFINITY)), ExpectedTxStart(T0)),
    )
    assert composed.source_evidence == ()


def test_a_first_write_a_flushed_insertion_authorized_stays_alone_with_its_anchor() -> None:
    authority = source_authority(POSITION, inserted_version=_unversioned)
    admission = _admitted(authority=authority)
    identity = admission.admit_insert(
        admitted_write(_position("insert", FEB, None, acctNum="A", value="100.00"), None, OBJECT),
        insertion_advice=None,
    )
    admission.drain_planned()
    authority.complete_write(
        WriteEffects(
            opened=Openings(continued=(TemporalRowCoordinates(ENTITY, (1,), OPEN_BITEMPORAL_ENDS),))
        ),
        (),
    )
    assert identity is not None
    _admit(
        admission,
        admitted_write(
            _position("amendUntil", FEB, JUN, value="150.00"), None, OBJECT, authority=identity
        ),
    )
    composed = _composition(admission)
    assert isinstance(composed, InsertionAuthorizedWrite)
    assert composed.intents == (
        InsertionAuthorizedIntent(WriteIntent("assignment", TimeInterval(FEB, JUN))),
    )
    assert composed.source_evidence == ()


@pytest.mark.parametrize("kind", ["observed-amendment", "observed-termination", "target"])
def test_a_lone_write_answers_what_its_one_intent_composition_holds(kind: str) -> None:
    # A repeat of the same write composes the two into one intent, which a
    # write still alone answers identically.
    source = _evidence(START)

    def write() -> AdmittedWrite:
        if kind == "target":
            return addressed_write(value="150.00")
        if kind == "observed-amendment":
            return _sourced("amendUntil", START, source, value="150.00")
        return _sourced("terminateUntil", START, source)

    alone = _composition(_admitted(write()))
    composed = _composition(_admitted(write(), write()))
    assert not isinstance(alone, ComposedTemporalWrite)
    assert isinstance(composed, ComposedTemporalWrite)
    assert alone.intents == composed.intents
    assert alone.transform == composed.transform
    assert (alone.target, alone.object_key, alone.phase) == (
        composed.target,
        composed.object_key,
        composed.phase,
    )
    assert [id(evidence) for evidence in alone.source_evidence] == [
        id(evidence) for evidence in composed.source_evidence
    ]


def test_a_second_write_composes_in_the_first_writes_place_keeping_its_authority() -> None:
    state = START.key
    assert isinstance(state, TemporalObjectStateKey)
    held = RetainedTargetState(state, 0, (), None)

    def retaining(item: TargetWrite) -> TargetWrite:
        return dataclasses.replace(item, retained=held)

    source = _evidence(LATER)
    admission = _admitted()
    admission.admit(addressed_write(until=JUN, value="150.00"), confirm_target=retaining)
    _admit(
        admission,
        _account_observed(7, 1),
        _sourced("amendUntil", LATER, source, valid_from=JUN, until=SEP, value="175.00"),
    )
    composed, other = admission.composed_writes()
    assert isinstance(composed, ComposedTemporalWrite)
    assert isinstance(other, StateObservedWrite)
    targeted, observed = composed.intents
    assert isinstance(targeted, TargetIntent) and targeted.retained is held
    assert isinstance(observed, StateObservedIntent) and observed.retained_observation is LATER
    assert len(composed.source_evidence) == 1 and composed.source_evidence[0] is source


def test_repeated_assignments_of_one_observation_and_window_keep_one_intent_in_place() -> None:
    source = _evidence(START)
    admission = _admitted(
        _sourced("amendUntil", START, source, value="150.00"),
        _account_observed(7, 1),
        _sourced("amendUntil", START, source, value="175.00"),
        _sourced("amendUntil", START, source, acctNum="B"),
    )
    composed, other = admission.composed_writes()
    assert isinstance(composed, ComposedTemporalWrite)
    assert isinstance(other, StateObservedWrite)
    (intent,) = _observed_intents(composed)
    assert intent.intent == WriteIntent("assignment", TimeInterval(MAR, SEP))
    assert len(intent.source_evidence) == 1 and intent.source_evidence[0] is source
    (segment,) = composed.transform.segments
    assert dict(segment.assigned or {}) == {"value": Decimal("175.00"), "acctNum": "B"}


def test_a_destruction_superseding_an_observed_run_moves_it_after_intervening_writes() -> None:
    earlier, later = _evidence(START), _evidence(START)
    assert earlier == later and earlier is not later
    admission = _admitted(
        _sourced("amendUntil", START, earlier, value="150.00"),
        _account_observed(7, 1),
        _sourced("terminateUntil", START, later),
    )
    other, composed = admission.composed_writes()
    assert isinstance(other, StateObservedWrite)
    assert isinstance(composed, ComposedTemporalWrite)
    assert composed.phase == "delete"
    (intent,) = _observed_intents(composed)
    assert intent.intent == WriteIntent("destructive", TimeInterval(MAR, SEP))
    # Every source survives by identity, first authored first.
    assert [id(evidence) for evidence in composed.source_evidence] == [id(earlier), id(later)]
    # A later write of the object meets the moved composition.
    _refused(admission, _sourced("amendUntil", START, later, value="1.00"))


def test_a_repeated_destruction_of_an_observed_run_stays_where_it_is() -> None:
    first, again = _evidence(START), _evidence(START)
    admission = _admitted(
        _sourced("terminateUntil", START, first),
        _account_observed(7, 1),
        _sourced("terminateUntil", START, again),
    )
    composed, other = admission.composed_writes()
    assert isinstance(composed, ComposedTemporalWrite)
    assert isinstance(other, StateObservedWrite)
    (intent,) = _observed_intents(composed)
    assert intent.intent.kind == "destructive"
    assert [id(evidence) for evidence in intent.source_evidence] == [id(first), id(again)]


def test_an_assignment_after_an_observed_runs_destruction_is_refused() -> None:
    source = _evidence(START)
    admission = _admitted(_sourced("terminateUntil", START, source))
    _refused(admission, _sourced("amendUntil", START, source, value="1.00"))
    (intent,) = _observed_intents(_composition(admission))
    assert intent.intent.kind == "destructive"


@pytest.mark.parametrize(
    ("observation", "valid_from", "until"),
    [
        (retained(rectangle(JAN, JUN, "100.00")), MAR, SEP),
        (START, MAR, JUN),
    ],
    ids=["equal-but-distinct-observation", "other-window"],
)
def test_an_observed_write_of_another_observation_or_window_composes_beside_the_run(
    observation: RetainedObservation, valid_from: dt.datetime, until: dt.datetime
) -> None:
    source = _evidence(START)
    admission = _admitted(
        _sourced("amendUntil", START, source, value="150.00"),
        _sourced(
            "amendUntil", observation, source, valid_from=valid_from, until=until, value="175.00"
        ),
    )
    held, arriving = _observed_intents(_composition(admission))
    assert held.retained_observation is START
    assert arriving.retained_observation is observation
    assert arriving.intent.valid_time_window == TimeInterval(valid_from, until)


def test_a_general_composition_keeps_every_later_observed_intent() -> None:
    source = _evidence(START)
    admission = _admitted(
        _sourced("amendUntil", START, source, value="150.00"),
        _sourced("amendUntil", LATER, _evidence(LATER), valid_from=JUN, until=SEP, value="2.00"),
        _sourced("amendUntil", START, source, value="175.00"),
    )
    intents = _observed_intents(_composition(admission))
    assert [intent.retained_observation for intent in intents] == [START, LATER, START]


@pytest.mark.parametrize(
    ("valid_from", "until", "admitted"),
    [(MAR, SEP, False), (JAN, FEB, True)],
    ids=["same-window", "disjoint-window"],
)
def test_a_write_holding_no_temporal_observation_states_no_start_beside_a_target(
    valid_from: dt.datetime, until: dt.datetime, admitted: bool
) -> None:
    # Planning refuses such a write; admission only finds that it states no
    # start a caller's condition could agree with, and no rectangle to
    # disagree with one over another window.
    write = observed_write("amendUntil", START, valid_from=valid_from, until=until, value="1.00")
    unobserved = RetainedObservation(
        VersionedObjectStateKey(OBJECT, 1), VersionObservation(observed_version=1), None
    )
    unclosable = admitted_write(write.instruction, unobserved, OBJECT)
    admission = _admitted(addressed_write(value="150.00"))
    if not admitted:
        _refused(admission, unclosable)
        return
    _admit(admission, unclosable)
    assert len(_composition(admission).intents) == 2
