"""The attempt's live write ownership (`m-unit-work`): the rows its settled writes
opened, the insertions it admitted and how much of each stays stored, and what
its completed writes left of the observed states its temporal sources share.

Insertions are opened, composed, and planned through real admission and
drain; every other fact is published by completion, as a successful settled
write publishes it. What an insertion left stored is observed through its
transitions: whether its authority still stands, and whether pending removals
reach everything it stored, so that a further insertion follows them. The
``OpenedRows`` fake the planning suites read is held to the same
``TemporalWriteOwnership`` answers here.
"""

from __future__ import annotations

import datetime as dt
import gc
from decimal import Decimal
from weakref import WeakValueDictionary

import pytest

from parallax.core import temporal_read
from parallax.core._execution._unit_work._errors import UnitOfWorkError
from parallax.core._execution._unit_work._write_ownership import (
    InsertionComposition,
    SourceRefusal,
    WriteOwnership,
)
from parallax.core._execution._unit_work.admission import WriteAdmission
from parallax.core._execution._unit_work.instructions import (
    PreparedKeyedInstruction,
    prepare_wire_write,
)
from parallax.core._execution._unit_work.retain import (
    NO_INSERTION_AUTHORITY,
    InsertionIdentity,
    KeyedWriteRefusalAdvice,
    ParticipationToken,
    ReadEvidence,
    RetainedObservation,
)
from parallax.core._execution._unit_work.write_items import (
    ComposedBitemporalOpening,
    InsertionAuthorizedWrite,
    KeyedInsert,
    TargetWrite,
)
from parallax.core.base import INFINITY, TemporalBound
from parallax.core.entity._model import model_of
from parallax.core.execution import KeyedWriteValueError
from parallax.core.metamodel import AttributeIdentity, EntityIdentity
from parallax.core.temporal_read import TimeInterval
from parallax.core.temporal_write.coverage import NO_TRANSFORM
from parallax.core.unit_work import KeyedWriteInstruction, admitted_write
from parallax.core.write_plan import PredecessorRow, TemporalObservation
from parallax.core.write_plan.keys import ObjectStateKey, object_state_key_from_observation
from parallax.core.write_plan.plan import (
    NO_OPENINGS,
    OPEN_BITEMPORAL_ENDS,
    TRANSACTION_TIME_ENDS,
    CurrentRowOutput,
    Derivation,
    DerivedRow,
    Openings,
    TemporalRowCoordinates,
)
from parallax.core.write_plan.steps import INFINITY as PLANNED_INFINITY
from parallax.core.write_plan.steps import NEW_LINEAGE, Finite, MaxPlusOne, PlannedRow, WriteRow
from tests.unit._corpus_identity_support import corpus_object_key
from tests.unit._where_position_model import WHERE_POSITION_META
from tests.unit.core._execution._unit_work._ownership_support import OpenedRows

_POSITION = model_of(WHERE_POSITION_META)
_KEY = corpus_object_key("WherePosition", ("id", 1))
_T0 = dt.datetime(2023, 12, 1, tzinfo=dt.UTC)
_SECOND_START = dt.datetime(2023, 12, 15, tzinfo=dt.UTC)
_REVISED_AT = dt.datetime(2024, 6, 1, tzinfo=dt.UTC)
_JAN, _FEB, _MAR, _APR, _MAY, _JUN, _AUG, _SEP = (
    dt.datetime(2024, month, 1, tzinfo=dt.UTC) for month in (1, 2, 3, 4, 5, 6, 8, 9)
)
_OPENER = KeyedWriteRefusalAdvice(
    not_stored="not stored", already_stored="already stored", repeated_insert="amend the opener"
)
_REPEATER = KeyedWriteRefusalAdvice(
    not_stored="not stored", already_stored="already stored", repeated_insert="amend the repeat"
)


def _confirmed(item: TargetWrite) -> TargetWrite:
    return item


def _no_version(entity: EntityIdentity, advanced_from: int | None) -> int | None:
    del entity, advanced_from
    return None


def _admission() -> WriteAdmission:
    return WriteAdmission(_POSITION, inserted_version=_no_version, observations={})


def _live(admission: WriteAdmission) -> WriteOwnership:
    ownership = admission.ownership
    assert isinstance(ownership, WriteOwnership)
    return ownership


def _insert(start: dt.datetime, until: dt.datetime | None = None) -> KeyedInsert:
    prepared = prepare_wire_write(
        KeyedWriteInstruction(
            "insert" if until is None else "insertUntil",
            "WherePosition",
            ({"id": 1, "acctNum": "A", "value": "1.00"},),
            start,
            until,
        ),
        _POSITION,
    )
    assert isinstance(prepared, PreparedKeyedInstruction)
    return admitted_write(prepared, None, _KEY)


def _stored(
    start: dt.datetime, until: dt.datetime | None = None
) -> tuple[WriteAdmission, InsertionIdentity]:
    admission = _admission()
    identity = admission.admit_insert(_insert(start, until), insertion_advice=None)
    assert identity is not None
    admission.drain_planned()
    return admission, identity


def _position_endpoint(end: dt.datetime | None) -> TemporalRowCoordinates:
    if end is None:
        return TemporalRowCoordinates(_KEY.entity, (1,), OPEN_BITEMPORAL_ENDS)
    return TemporalRowCoordinates(_KEY.entity, (1,), (Finite(instant=end), PLANNED_INFINITY))


def _shape() -> temporal_read.TemporalShape:
    shape = temporal_read.view(_POSITION).shape(_KEY.entity)
    assert shape is not None
    return shape


def _observed(start: dt.datetime, tx_start: dt.datetime = _T0) -> RetainedObservation:
    row = PredecessorRow(
        members={
            "id": 1,
            "acctNum": "A",
            "value": Decimal("100.00"),
            "validStart": start,
            "validEnd": INFINITY,
            "txStart": tx_start,
            "txEnd": INFINITY,
        }
    )
    observation = TemporalObservation(predecessor=row)
    return RetainedObservation(
        object_state_key_from_observation(_KEY, observation, _shape()), observation, None
    )


def _state(start: dt.datetime, tx_start: dt.datetime) -> ObjectStateKey:
    return _observed(start, tx_start).key


def _follows_removal(
    ownership: WriteOwnership,
    start: dt.datetime,
    end: dt.datetime | TemporalBound,
) -> bool:
    """Whether a further insertion, beside pending writes destroying
    ``[start, end)`` of the object, is a first opening that follows them: the
    removal reaches everything the object's admissions left stored."""
    assert end is INFINITY or isinstance(end, dt.datetime)
    _identity, follows = ownership.open_insertion(
        _insert(_SEP),
        pending_removal=NO_TRANSFORM.followed_by(TimeInterval(start, end), None, replaces=False),
        removes_object=False,
        insertion_advice=None,
    )
    return follows


# --------------------------------------------------------------------------- #
# Owned rows and the insertions they continue.                                #
# --------------------------------------------------------------------------- #
def test_a_row_a_settled_write_removes_and_reopens_at_one_address_stays_owned() -> None:
    # Removals are retired before openings register, so the row a settled write
    # reopened at the address it removed is still the attempt's to revise.
    endpoint = TemporalRowCoordinates(_KEY.entity, (1,), (Finite(instant=_JUN), PLANNED_INFINITY))
    ownership = WriteOwnership(_POSITION, version_after=_no_version, observations={})
    ownership.complete((), Openings(fresh=(endpoint,)))
    ownership.complete((endpoint,), Openings(fresh=(endpoint,)))
    assert ownership.owns(endpoint)


def _cancel_reinsertion(admission: WriteAdmission, start: dt.datetime) -> InsertionIdentity:
    """Insert the stored object again at ``start`` and terminate that pending
    opening whole through the identity it issued, answering that identity."""
    identity = admission.admit_insert(_insert(start), insertion_advice=None)
    assert identity is not None
    termination = prepare_wire_write(
        KeyedWriteInstruction("terminate", "WherePosition", ({"id": 1},), start), _POSITION
    )
    assert isinstance(termination, PreparedKeyedInstruction)
    admission.admit(
        InsertionAuthorizedWrite(termination, _KEY, identity), confirm_target=_confirmed
    )
    return identity


def _stored_through(stage: str) -> WriteOwnership:
    """An insertion stored from February, whose open row a later write bounds
    at June, then admitted again from April and drained, then reinserted
    from May and cancelled, as far as ``stage``."""
    admission, stored = _stored(_FEB)
    ownership = _live(admission)
    open_row = _position_endpoint(None)
    ownership.complete((), Openings(continued=(open_row,)))
    if stage == "open":
        return ownership
    ownership.complete((open_row,), Openings(continued=(_position_endpoint(_JUN),)))
    if stage == "bounded":
        return ownership
    # A stored object's further admission keeps its anchor until its buffer
    # is drained, and supersedes the earlier insertion's authority.
    further = admission.admit_insert(_insert(_APR), insertion_advice=None)
    assert further is not None
    admission.drain_planned()
    assert ownership.insertion_authority(stored) is NO_INSERTION_AUTHORITY
    if stage == "drained":
        return ownership
    # Composition cancelling a pending one changes neither tags nor anchor.
    cancelled = _cancel_reinsertion(admission, _MAY)
    assert ownership.insertion_authority(cancelled) is NO_INSERTION_AUTHORITY
    assert ownership.insertion_authority(further) is NO_INSERTION_AUTHORITY
    return ownership


@pytest.mark.parametrize(
    ("stage", "start", "end", "follows"),
    [
        ("open", _FEB, INFINITY, True),
        ("open", _MAR, INFINITY, False),
        ("open", _FEB, _SEP, False),
        ("bounded", _FEB, _JUN, True),
        ("bounded", _FEB, _MAY, False),
        ("bounded", _MAR, _JUN, False),
        ("drained", _MAR, _JUN, True),
        ("drained", _MAY, _JUN, False),
        ("cancelled", _MAR, _JUN, True),
        ("cancelled", _MAY, _JUN, False),
    ],
)
def test_a_stored_insertion_is_removed_whole_from_its_anchor_to_its_latest_row_end(
    stage: str, start: dt.datetime, end: dt.datetime | TemporalBound, follows: bool
) -> None:
    assert _follows_removal(_stored_through(stage), start, end) is follows


def test_an_insertion_keeps_only_its_own_part_of_a_merged_row_and_ends_with_it() -> None:
    admission, identity = _stored(_JAN, _APR)
    ownership = _live(admission)
    merged = _position_endpoint(_JUN)
    ownership.complete((), Openings(shared=((merged, (TimeInterval(_JAN, _APR),)),)))
    assert ownership.continues_insertion(merged)
    assert ownership.insertion_coverage(merged, TimeInterval(_JAN, _JUN)) == (
        TimeInterval(_JAN, _APR),
    )
    assert ownership.insertion_authority(identity) == TimeInterval(_JAN, _APR)
    # Revised in place to [April, June), the row holds none of its part.
    ownership.complete((), Openings(fresh=(merged,)))
    assert not ownership.continues_insertion(merged)
    assert ownership.owns(merged)
    assert ownership.insertion_authority(identity) is NO_INSERTION_AUTHORITY


@pytest.mark.parametrize(("end", "follows"), [(_APR, True), (_MAR, False)])
def test_an_insertions_removal_ends_where_its_part_of_a_merged_row_does(
    end: dt.datetime, follows: bool
) -> None:
    admission, _identity = _stored(_JAN, _APR)
    ownership = _live(admission)
    merged = _position_endpoint(_JUN)
    ownership.complete((), Openings(shared=((merged, (TimeInterval(_JAN, _APR),)),)))
    assert _follows_removal(ownership, _JAN, end) is follows


def test_a_row_still_holding_part_of_an_insertion_keeps_it_standing() -> None:
    admission, identity = _stored(_JAN, _APR)
    ownership = _live(admission)
    merged = _position_endpoint(_JUN)
    ownership.complete((), Openings(shared=((merged, (TimeInterval(_JAN, _APR),)),)))
    narrowed = (TimeInterval(_FEB, _APR),)
    ownership.complete((), Openings(shared=((merged, narrowed),)))
    assert ownership.insertion_coverage(merged, TimeInterval(_FEB, _JUN)) == narrowed
    assert ownership.insertion_authority(identity) == TimeInterval(_JAN, _APR)
    # Whole again once a successor lies inside the part it contributed.
    head = _position_endpoint(_FEB)
    ownership.complete((merged,), Openings(continued=(head,)))
    assert ownership.insertion_coverage(head, TimeInterval(_JAN, _FEB)) == (
        TimeInterval(_JAN, _FEB),
    )
    assert ownership.insertion_authority(identity) == TimeInterval(_JAN, _APR)


@pytest.mark.parametrize(("end", "follows"), [(INFINITY, True), (_SEP, False)])
def test_an_insertions_part_running_on_without_end_leaves_its_removal_open(
    end: dt.datetime | TemporalBound, follows: bool
) -> None:
    admission, _identity = _stored(_JAN, _APR)
    ownership = _live(admission)
    merged = _position_endpoint(None)
    untagged = _position_endpoint(_JAN)
    ownership.complete(
        (), Openings(fresh=(untagged,), shared=((merged, (TimeInterval(_APR, INFINITY),)),))
    )
    assert ownership.insertion_coverage(untagged, TimeInterval(_JAN, _FEB)) == ()
    assert _follows_removal(ownership, _JAN, end) is follows


def test_a_row_named_again_after_its_insertion_ended_is_no_longer_tagged() -> None:
    admission, stored = _stored(_JAN, _APR)
    ownership = _live(admission)
    row = _position_endpoint(_APR)
    ownership.complete((), Openings(continued=(row,)))
    cancelled = _cancel_reinsertion(admission, _FEB)
    assert ownership.insertion_authority(stored) is NO_INSERTION_AUTHORITY
    assert ownership.insertion_authority(cancelled) is NO_INSERTION_AUTHORITY
    assert ownership.continues_insertion(row)
    ownership.complete((), Openings(continued=(row,)))
    assert not ownership.continues_insertion(row)
    assert ownership.owns(row)
    # The attempt still admitted an insertion of the object.
    assert ownership.has_admitted_insertion(_KEY)


# --------------------------------------------------------------------------- #
# An insertion's lifecycle moves only through its named transitions.          #
# --------------------------------------------------------------------------- #
def test_a_repeat_of_a_standing_insertion_is_refused_with_its_openers_advice() -> None:
    ownership = WriteOwnership(_POSITION, version_after=_no_version, observations={})
    identity, follows = ownership.open_insertion(
        _insert(_FEB), pending_removal=None, removes_object=False, insertion_advice=_OPENER
    )
    assert not follows
    for stored in (False, True):
        if stored:
            ownership.finish_insertion_planning(pending_keys=(_KEY,), removed_objects=())
            ownership.complete((), Openings(continued=(_position_endpoint(None),)))
        with pytest.raises(KeyedWriteValueError) as refusal:
            ownership.open_insertion(
                _insert(_FEB),
                pending_removal=NO_TRANSFORM.followed_by(
                    TimeInterval(_MAR, INFINITY), None, replaces=False
                ),
                removes_object=False,
                insertion_advice=_REPEATER,
            )
        assert refusal.value.code == "write-value-already-stored"
        assert refusal.value.message.endswith("amend the opener")
        assert ownership.insertion_authority(identity) == TimeInterval(_FEB, INFINITY)


def test_a_reinsertion_supersedes_the_identity_before_it_and_issues_its_own() -> None:
    admission, first = _stored(_FEB)
    ownership = _live(admission)
    ownership.complete((), Openings(continued=(_position_endpoint(None),)))
    second, follows = ownership.open_insertion(
        _insert(_APR),
        pending_removal=NO_TRANSFORM.followed_by(
            TimeInterval(_FEB, INFINITY), None, replaces=False
        ),
        removes_object=False,
        insertion_advice=None,
    )
    assert follows and second is not first
    assert ownership.insertion_authority(first) is NO_INSERTION_AUTHORITY
    assert ownership.insertion_authority(second) == TimeInterval(_APR, INFINITY)
    amendment = prepare_wire_write(
        KeyedWriteInstruction("amend", "WherePosition", ({"id": 1, "value": "2.00"},), _FEB),
        _POSITION,
    )
    assert isinstance(amendment, PreparedKeyedInstruction)
    with pytest.raises(UnitOfWorkError, match="no longer stands"):
        ownership.resolve_insertion_authorized_write(
            InsertionAuthorizedWrite(amendment, _KEY, first)
        )


def test_an_ended_opening_retires_its_identity_and_its_reinsertion_follows_it() -> None:
    ownership = WriteOwnership(_POSITION, version_after=_no_version, observations={})
    insert = _insert(_FEB, _JUN)
    identity, _follows = ownership.open_insertion(
        insert, pending_removal=None, removes_object=False, insertion_advice=_OPENER
    )
    replacement = prepare_wire_write(
        KeyedWriteInstruction(
            "replaceUntil",
            "WherePosition",
            ({"id": 1, "acctNum": "B", "value": "2.00"},),
            _FEB,
            _SEP,
        ),
        _POSITION,
    )
    destruction = prepare_wire_write(
        KeyedWriteInstruction("terminateUntil", "WherePosition", ({"id": 1},), _FEB, _SEP),
        _POSITION,
    )
    assert isinstance(replacement, PreparedKeyedInstruction)
    assert isinstance(destruction, PreparedKeyedInstruction)
    # A replacement reaching past the opening, then a destruction of all it
    # reached, leave nothing of the opening while stored coverage past it is
    # still replaced.
    opening = ComposedBitemporalOpening(insert=insert, transform=NO_TRANSFORM, intents=())
    opening = opening.followed_by(replacement, "id").followed_by(destruction, "id")
    assert opening.beyond is not None
    arriving = InsertionAuthorizedWrite(destruction, _KEY, identity)
    composition = ownership.apply_insertion_composition(
        _KEY, arriving=arriving, proposed_opening=opening
    )
    assert composition is InsertionComposition.ENDED
    assert ownership.insertion_authority(identity) is NO_INSERTION_AUTHORITY
    # The ended opening refuses no repeat, and the next insertion follows it.
    again, follows = ownership.open_insertion(
        _insert(_FEB), pending_removal=None, removes_object=False, insertion_advice=_REPEATER
    )
    assert follows and again is not identity


# --------------------------------------------------------------------------- #
# What completed writes left of the observed states live sources share.       #
# --------------------------------------------------------------------------- #
type _Index = WeakValueDictionary[ObjectStateKey, RetainedObservation]


def _observing(*observations: RetainedObservation) -> tuple[WriteOwnership, _Index]:
    index: _Index = WeakValueDictionary()
    for observation in observations:
        index[observation.key] = observation
    return WriteOwnership(_POSITION, version_after=_no_version, observations=index), index


def _parts(
    coverage: TimeInterval, *rows: tuple[TemporalRowCoordinates, TimeInterval]
) -> tuple[DerivedRow, ...]:
    return tuple(
        DerivedRow(coordinates, extent, extent.intersection(coverage))
        for coordinates, extent in rows
    )


def _derived(
    predecessor: ObjectStateKey,
    coverage: TimeInterval,
    *rows: tuple[TemporalRowCoordinates, TimeInterval],
    input_coordinates: TemporalRowCoordinates | None = None,
) -> Derivation:
    return Derivation(predecessor, coverage, input_coordinates, _parts(coverage, *rows))


_VALUE = AttributeIdentity(_KEY.entity, "value")


def _output(
    coordinates: TemporalRowCoordinates, coverage: TimeInterval, value: str
) -> CurrentRowOutput:
    row = WriteRow(row=PlannedRow(attributes={_VALUE: Decimal(value)}), origin=NEW_LINEAGE)
    return CurrentRowOutput(
        coordinates=coordinates, valid_time_coverage=coverage, row=row, emitter=row
    )


def _values(ownership: WriteOwnership, window: TimeInterval | None) -> list[object]:
    return [row.member("value") for row in ownership.current_rows(_KEY, window)]


def test_a_live_observations_changed_state_continues_only_where_its_parts_survive() -> None:
    observed = _observed(_JAN)
    ownership, _index = _observing(observed)
    head, tail = _position_endpoint(_FEB), _position_endpoint(None)
    assert ownership.continues(observed, _JUN) is None
    assert ownership.demanded(observed.key, None)
    # Terminated over [February, April): the parts before and after survive.
    ownership.complete(
        (),
        Openings(fresh=(head, tail)),
        (
            _derived(
                observed.key,
                TimeInterval(_JAN, INFINITY),
                (head, TimeInterval(_JAN, _FEB)),
                (tail, TimeInterval(_APR, INFINITY)),
            ),
        ),
    )
    assert ownership.continues(observed, _JAN) is True
    assert ownership.continues(observed, dt.datetime(2024, 3, 1, tzinfo=dt.UTC)) is False
    assert ownership.continues(observed, _JUN) is True
    assert ownership.continues(observed, None) is True
    # Its changed state no longer needs telling apart; its rows do.
    assert not ownership.demanded(observed.key, None)
    assert ownership.demanded(_state(_APR, _REVISED_AT), tail)
    assert ownership.continues(_observed(_JAN), _JUN) is None


def test_a_changed_state_its_write_left_nothing_of_has_ended_everywhere() -> None:
    observed = _observed(_JAN)
    ownership, _index = _observing(observed)
    ownership.complete(
        (), NO_OPENINGS, (Derivation(observed.key, TimeInterval(_JAN, INFINITY), None, ()),)
    )
    assert ownership.continues(observed, _JUN) is False
    assert ownership.continues(observed, None) is False


def test_an_unobserved_descendant_carries_its_origin_through_every_later_change() -> None:
    observed = _observed(_JAN)
    ownership, _index = _observing(observed)
    whole = _position_endpoint(None)
    ownership.complete(
        (),
        Openings(fresh=(whole,)),
        (
            _derived(
                observed.key, TimeInterval(_JAN, INFINITY), (whole, TimeInterval(_JAN, INFINITY))
            ),
        ),
    )
    # No read observes the row it produced; a later write splits that row,
    # and the origin follows each part it still contributes.
    head = _position_endpoint(_JUN)
    ownership.complete(
        (),
        Openings(fresh=(head,)),
        (
            _derived(
                _state(_JAN, _REVISED_AT),
                TimeInterval(_JAN, INFINITY),
                (head, TimeInterval(_JAN, _JUN)),
                (whole, TimeInterval(_AUG, INFINITY)),
                input_coordinates=whole,
            ),
        ),
    )
    assert ownership.continues(observed, _FEB) is True
    assert ownership.continues(observed, dt.datetime(2024, 7, 1, tzinfo=dt.UTC)) is False
    assert ownership.continues(observed, _SEP) is True


def test_a_fresh_observation_of_a_produced_row_joins_the_origin_it_descends_from() -> None:
    first = _observed(_JAN)
    ownership, index = _observing(first)
    produced = _position_endpoint(None)
    ownership.complete(
        (),
        Openings(fresh=(produced,)),
        (
            _derived(
                first.key, TimeInterval(_JAN, INFINITY), (produced, TimeInterval(_APR, INFINITY))
            ),
        ),
    )
    # A fresh read observes the whole produced row, beginning in January only
    # where the earlier write filled in what the first never held.
    second = _observed(_JAN, _REVISED_AT)
    index[second.key] = second
    narrowed = _position_endpoint(_JUN)
    ownership.complete(
        (),
        Openings(fresh=(narrowed,)),
        (
            _derived(
                second.key,
                TimeInterval(_JAN, INFINITY),
                (narrowed, TimeInterval(_JAN, _JUN)),
                input_coordinates=produced,
            ),
        ),
    )
    assert ownership.continues(second, _FEB) is True
    assert ownership.continues(first, _FEB) is False
    assert ownership.continues(first, _MAY) is True
    assert ownership.continues(first, _JUN) is False


def test_one_origins_adjacent_parts_of_a_merged_row_are_one_contribution() -> None:
    observed = _observed(_JAN)
    ownership, _index = _observing(observed)
    left, right = _position_endpoint(_APR), _position_endpoint(_JUN)
    ownership.complete(
        (),
        Openings(fresh=(left, right)),
        (
            _derived(
                observed.key,
                TimeInterval(_JAN, _JUN),
                (left, TimeInterval(_JAN, _APR)),
                (right, TimeInterval(_APR, _JUN)),
            ),
        ),
    )
    merged = TimeInterval(_JAN, _JUN)
    ownership.complete(
        (left,),
        NO_OPENINGS,
        (
            Derivation(
                _state(_JAN, _REVISED_AT),
                TimeInterval(_JAN, _APR),
                left,
                (DerivedRow(right, merged, TimeInterval(_JAN, _APR)),),
            ),
            Derivation(
                _state(_APR, _REVISED_AT),
                TimeInterval(_APR, _JUN),
                right,
                (DerivedRow(right, merged, TimeInterval(_APR, _JUN)),),
            ),
        ),
    )
    held = ownership._contributions[right]  # pyright: ignore[reportPrivateUsage] - the reverse view
    assert [(contribution.coverage) for contribution in held] == [merged]


def test_coverage_a_later_write_fills_revives_no_part_of_an_ended_origin() -> None:
    observed = _observed(_JAN)
    ownership, _index = _observing(observed)
    head = _position_endpoint(_FEB)
    ownership.complete(
        (),
        Openings(fresh=(head,)),
        (_derived(observed.key, TimeInterval(_JAN, INFINITY), (head, TimeInterval(_JAN, _FEB))),),
    )
    # The rest is filled again by a new lineage, which no observed state
    # contributed to.
    ownership.complete((), Openings(fresh=(_position_endpoint(None),)))
    assert ownership.continues(observed, _JUN) is False
    assert ownership.continues(observed, _JAN) is True


def test_only_captured_rows_a_surviving_part_reaches_are_held_and_found_by_window() -> None:
    observed = _observed(_JAN)
    ownership, _index = _observing(observed)
    head, middle, tail = (
        _position_endpoint(_FEB),
        _position_endpoint(_JUN),
        _position_endpoint(None),
    )
    ownership.complete(
        (),
        Openings(fresh=(head, middle, tail)),
        (
            _derived(
                observed.key,
                TimeInterval(_JAN, _JUN),
                (head, TimeInterval(_JAN, _FEB)),
                (middle, TimeInterval(_FEB, _JUN)),
            ),
        ),
        (
            (_output(head, TimeInterval(_JAN, _FEB), "1.00"), None),
            (_output(middle, TimeInterval(_FEB, _JUN), "2.00"), None),
            (_output(tail, TimeInterval(_JUN, INFINITY), "3.00"), None),
        ),
    )
    assert _values(ownership, None) == [Decimal("1.00"), Decimal("2.00")]
    assert _values(ownership, TimeInterval(_FEB, _SEP)) == [Decimal("2.00")]
    assert _values(ownership, TimeInterval(_JUN, _SEP)) == []
    assert _values(ownership, TimeInterval(dt.datetime(2024, 1, 15, tzinfo=dt.UTC), _APR)) == [
        Decimal("1.00"),
        Decimal("2.00"),
    ]
    # Revising the middle row in place replaces what is held for it; one the
    # write removed is held no longer.
    ownership.complete(
        (head,),
        NO_OPENINGS,
        (
            _derived(
                _state(_FEB, _REVISED_AT),
                TimeInterval(_FEB, _JUN),
                (middle, TimeInterval(_FEB, _JUN)),
                input_coordinates=middle,
            ),
        ),
        ((_output(middle, TimeInterval(_FEB, _JUN), "4.00"), None),),
    )
    assert _values(ownership, None) == [Decimal("4.00")]


def test_a_changed_row_whose_execution_captured_nothing_is_held_no_longer() -> None:
    observed = _observed(_JAN)
    ownership, _index = _observing(observed)
    whole = _position_endpoint(None)
    ownership.complete(
        (),
        Openings(fresh=(whole,)),
        (
            _derived(
                observed.key, TimeInterval(_JAN, INFINITY), (whole, TimeInterval(_JAN, INFINITY))
            ),
        ),
        ((_output(whole, TimeInterval(_JAN, INFINITY), "1.00"), None),),
    )
    ownership.complete(
        (),
        NO_OPENINGS,
        (
            _derived(
                _state(_JAN, _REVISED_AT),
                TimeInterval(_JAN, INFINITY),
                (whole, TimeInterval(_JAN, INFINITY)),
                input_coordinates=whole,
            ),
        ),
    )
    assert _values(ownership, None) == []
    assert ownership.continues(observed, _JUN) is True


def test_what_an_observation_left_is_released_when_it_is_collected() -> None:
    observed = _observed(_JAN)
    ownership, _index = _observing(observed)
    whole = _position_endpoint(None)
    ownership.complete(
        (),
        Openings(fresh=(whole,)),
        (
            _derived(
                observed.key, TimeInterval(_JAN, INFINITY), (whole, TimeInterval(_JAN, INFINITY))
            ),
        ),
        ((_output(whole, TimeInterval(_JAN, INFINITY), "1.00"), None),),
    )
    assert _values(ownership, None) == [Decimal("1.00")]
    del observed
    gc.collect()
    assert _values(ownership, None) == []
    assert not ownership.demanded(_state(_JAN, _REVISED_AT), whole)
    assert ownership._origins == {}  # pyright: ignore[reportPrivateUsage] - nothing left of it


def test_an_observation_collected_while_a_completion_runs_is_pruned_once_it_is_done() -> None:
    observed = _observed(_JAN)
    ownership, _index = _observing(observed)
    whole = _position_endpoint(None)
    ownership.complete(
        (),
        Openings(fresh=(whole,)),
        (
            _derived(
                observed.key, TimeInterval(_JAN, INFINITY), (whole, TimeInterval(_JAN, INFINITY))
            ),
        ),
        ((_output(whole, TimeInterval(_JAN, INFINITY), "1.00"), None),),
    )
    (origin,) = ownership._origins.values()  # pyright: ignore[reportPrivateUsage] - its one origin
    ownership._updating = True  # pyright: ignore[reportPrivateUsage] - as a completion runs
    ownership._prune_origin(origin)  # pyright: ignore[reportPrivateUsage] - its callback, early
    assert _values(ownership, None) == [Decimal("1.00")]
    ownership._updating = False  # pyright: ignore[reportPrivateUsage] - the completion ends
    ownership._drain_prunes()  # pyright: ignore[reportPrivateUsage] - as completion drains
    assert _values(ownership, None) == []


def test_clearing_releases_every_origin_and_held_row() -> None:
    observed = _observed(_JAN)
    ownership, _index = _observing(observed)
    whole = _position_endpoint(None)
    ownership.complete(
        (),
        Openings(fresh=(whole,)),
        (
            _derived(
                observed.key, TimeInterval(_JAN, INFINITY), (whole, TimeInterval(_JAN, INFINITY))
            ),
        ),
        ((_output(whole, TimeInterval(_JAN, INFINITY), "1.00"), None),),
    )
    ownership.clear()
    assert ownership.continues(observed, None) is None
    assert _values(ownership, None) == []


def test_fresh_and_continuing_origins_of_one_row_propagate_together_through_splits() -> None:
    first = _observed(_JAN)
    ownership, index = _observing(first)
    head, tail = _position_endpoint(_APR), _position_endpoint(None)
    ownership.complete(
        (),
        Openings(fresh=(head, tail)),
        (
            _derived(
                first.key,
                TimeInterval(_JAN, INFINITY),
                (head, TimeInterval(_JAN, _APR)),
                (tail, TimeInterval(_APR, INFINITY)),
            ),
        ),
    )
    # A fresh read observes the produced tail, which still carries the first
    # observation's part: a split of it carries both.
    second = _observed(_APR, _REVISED_AT)
    index[second.key] = second
    middle = _position_endpoint(_JUN)
    ownership.complete(
        (),
        Openings(fresh=(middle,)),
        (
            _derived(
                second.key,
                TimeInterval(_APR, INFINITY),
                (middle, TimeInterval(_APR, _JUN)),
                (tail, TimeInterval(_JUN, INFINITY)),
                input_coordinates=tail,
            ),
        ),
    )
    # The head and the middle merge, then split again at February: the part
    # before February takes the first origin alone.
    merged = TimeInterval(_JAN, _JUN)
    ownership.complete(
        (head,),
        NO_OPENINGS,
        (
            Derivation(
                _state(_JAN, _REVISED_AT),
                TimeInterval(_JAN, _APR),
                head,
                (DerivedRow(middle, merged, TimeInterval(_JAN, _APR)),),
            ),
            Derivation(
                _state(_APR, _REVISED_AT),
                TimeInterval(_APR, _JUN),
                middle,
                (DerivedRow(middle, merged, TimeInterval(_APR, _JUN)),),
            ),
        ),
    )
    early = _position_endpoint(_FEB)
    ownership.complete(
        (),
        Openings(fresh=(early,)),
        (
            _derived(
                _state(_JAN, _REVISED_AT),
                merged,
                (early, TimeInterval(_JAN, _FEB)),
                (middle, TimeInterval(_FEB, _JUN)),
                input_coordinates=middle,
            ),
        ),
    )
    contributions = ownership._contributions  # pyright: ignore[reportPrivateUsage] - the reverse view
    assert [part.coverage for part in contributions[early]] == [TimeInterval(_JAN, _FEB)]
    assert sorted(
        (part.origin() is second, part.coverage.start)
        for part in contributions[middle]
        if part.coverage is not None
    ) == [(False, _FEB), (True, _APR)]
    assert ownership.continues(first, _JAN) is True
    assert ownership.continues(first, _JUN) is True
    assert ownership.continues(second, _FEB) is False
    assert ownership.continues(second, _MAY) is True
    assert ownership.continues(second, _SEP) is True


def test_a_row_holding_a_generated_value_is_not_held_however_a_part_reaches_it() -> None:
    observed = _observed(_JAN)
    ownership, _index = _observing(observed)
    whole = _position_endpoint(None)
    generated = WriteRow(
        row=PlannedRow(attributes={_VALUE: MaxPlusOne()}),
        origin=NEW_LINEAGE,
    )
    ownership.complete(
        (),
        Openings(fresh=(whole,)),
        (
            _derived(
                observed.key, TimeInterval(_JAN, INFINITY), (whole, TimeInterval(_JAN, INFINITY))
            ),
        ),
        (
            (
                CurrentRowOutput(
                    coordinates=whole,
                    valid_time_coverage=TimeInterval(_JAN, INFINITY),
                    row=generated,
                    emitter=generated,
                ),
                None,
            ),
        ),
    )
    assert ownership.continues(observed, _JUN) is True
    assert _values(ownership, None) == []


def test_a_stale_temporal_source_reaches_nothing_and_a_live_one_its_own_state() -> None:
    participation = ParticipationToken()
    observed = _observed(_JAN)
    ownership, _index = _observing(observed)
    fresh = ReadEvidence(_KEY.entity, _KEY, participation, observed)
    assert ownership.resolve_source(fresh) is observed
    # Published from rows read before a completed change, its observation was
    # never indexed, so no completed write recorded anything of it.
    stale = _observed(_JAN)
    stale.invalidate()
    assert (
        ownership.resolve_source(ReadEvidence(_KEY.entity, _KEY, participation, stale))
        is SourceRefusal.STALE
    )


def test_an_observation_collected_after_its_ownership_was_cleared_prunes_nothing() -> None:
    observed = _observed(_JAN)
    ownership, _index = _observing(observed)
    whole = _position_endpoint(None)
    ownership.complete(
        (),
        Openings(fresh=(whole,)),
        (
            _derived(
                observed.key, TimeInterval(_JAN, INFINITY), (whole, TimeInterval(_JAN, INFINITY))
            ),
        ),
    )
    (origin,) = ownership._origins.values()  # pyright: ignore[reportPrivateUsage] - its one origin
    ownership.clear()
    ownership._forget_origin(origin)  # pyright: ignore[reportPrivateUsage] - its callback, late
    assert ownership._origins == {}  # pyright: ignore[reportPrivateUsage] - nothing came back
    assert ownership.continues(observed, None) is None


def test_a_transaction_time_origin_continues_while_its_one_row_survives() -> None:
    log = EntityIdentity("parallax.compatibility", "TransactionLog")
    row = TemporalRowCoordinates(log, (1,), TRANSACTION_TIME_ENDS)
    observed = _observed(_JAN)
    ownership, _index = _observing(observed)
    ownership.complete(
        (),
        Openings(fresh=(row,)),
        (Derivation(observed.key, None, None, (DerivedRow(row, None, None),)),),
    )
    assert ownership.continues(observed, None) is True
    ownership.complete((row,), NO_OPENINGS, (Derivation(_state(_JAN, _REVISED_AT), None, row, ()),))
    assert ownership.continues(observed, None) is False


# --------------------------------------------------------------------------- #
# The fake planning suites read answers as production does.                   #
# --------------------------------------------------------------------------- #
def test_the_fake_answers_only_the_part_of_an_insertion_a_row_covers() -> None:
    admission, _identity = _stored(_JAN, _APR)
    production = _live(admission)
    first, second = _position_endpoint(_APR), _position_endpoint(_JUN)
    parts = (TimeInterval(_JAN, _FEB), TimeInterval(_MAY, _JUN))
    for endpoint in (first, second):
        production.complete((), Openings(shared=((endpoint, parts),)))
    fake = OpenedRows(frozenset({first, second}), frozenset({first, second}), insertion_parts=parts)
    for endpoint, coverage in (
        (first, TimeInterval(_JAN, _APR)),
        (second, TimeInterval(_APR, _JUN)),
    ):
        assert fake.insertion_coverage(endpoint, coverage) == production.insertion_coverage(
            endpoint, coverage
        )
    assert fake.insertion_coverage(first, TimeInterval(_JAN, _APR)) == (TimeInterval(_JAN, _FEB),)
