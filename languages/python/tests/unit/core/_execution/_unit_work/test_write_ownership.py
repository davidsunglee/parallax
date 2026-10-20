"""The attempt's live write ownership (`m-unit-work`): the rows its units
opened, the insertions it admitted and how much of each stays stored, and what
the running flush's units proved for later ones.

Insertion records come from real admission and drain; every other fact is
published by completion, as a successful unit publishes it. The
``OpenedRows`` fake the planning suites read is held to the same
``TemporalWriteOwnership`` answers here.
"""

from __future__ import annotations

import datetime as dt
from decimal import Decimal

import pytest

from parallax.core import temporal_read
from parallax.core._execution._unit_work._write_ownership import InsertionRecord, WriteOwnership
from parallax.core._execution._unit_work.admission import WriteAdmission
from parallax.core._execution._unit_work.instructions import PreparedKeyedWrite, prepare_wire_write
from parallax.core._execution._unit_work.write_items import InsertionKeyedWrite, TargetKeyedWrite
from parallax.core.base import INFINITY
from parallax.core.entity._model import model_of
from parallax.core.metamodel import EntityIdentity
from parallax.core.temporal_read import TimeInterval
from parallax.core.unit_work import KeyedWriteInstruction
from parallax.core.write_plan import PredecessorRow, TemporalObservation
from parallax.core.write_plan.keys import ObjectStateKey, object_state_key_from_observation
from parallax.core.write_plan.plan import (
    NO_OPENINGS,
    OPEN_BITEMPORAL_ENDS,
    TRANSACTION_TIME_ENDS,
    Derivation,
    DerivedRow,
    Openings,
    OwnedEndpoint,
    TemporalWriteOwnership,
)
from parallax.core.write_plan.steps import INFINITY as PLANNED_INFINITY
from parallax.core.write_plan.steps import Finite
from tests.unit._corpus_identity_support import corpus_object_key
from tests.unit._where_position_model import WHERE_POSITION_META
from tests.unit.core._execution._unit_work._ownership_support import OpenedRows

_POSITION = model_of(WHERE_POSITION_META)
_KEY = corpus_object_key("WherePosition", ("id", 1))
_T0 = dt.datetime(2023, 12, 1, tzinfo=dt.UTC)
_SECOND_START = dt.datetime(2023, 12, 15, tzinfo=dt.UTC)
_REVISED_AT = dt.datetime(2024, 6, 1, tzinfo=dt.UTC)
_JAN, _FEB, _APR, _MAY, _JUN, _AUG, _SEP = (
    dt.datetime(2024, month, 1, tzinfo=dt.UTC) for month in (1, 2, 4, 5, 6, 8, 9)
)


def _confirmed(item: TargetKeyedWrite) -> TargetKeyedWrite:
    return item


def _no_version(entity: EntityIdentity, advanced_from: int | None) -> int | None:
    del entity, advanced_from
    return None


def _admission() -> WriteAdmission:
    return WriteAdmission(_POSITION, inserted_version=_no_version)


def _live(admission: WriteAdmission) -> WriteOwnership:
    ownership = admission.ownership
    assert isinstance(ownership, WriteOwnership)
    return ownership


def _insert(start: dt.datetime, until: dt.datetime | None = None) -> PreparedKeyedWrite:
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
    assert isinstance(prepared, PreparedKeyedWrite)
    return prepared


def _stored(
    start: dt.datetime, until: dt.datetime | None = None
) -> tuple[WriteAdmission, InsertionRecord]:
    admission = _admission()
    admission.admit(_insert(start, until), confirm_target=_confirmed)
    admission.drain_planned()
    record = _live(admission).insertion_record(_KEY)
    assert record is not None
    return admission, record


def _position_endpoint(end: dt.datetime | None) -> OwnedEndpoint:
    if end is None:
        return OwnedEndpoint(_KEY.entity, (1,), OPEN_BITEMPORAL_ENDS)
    return OwnedEndpoint(_KEY.entity, (1,), (Finite(instant=end), PLANNED_INFINITY))


def _shape() -> temporal_read.TemporalShape:
    shape = temporal_read.view(_POSITION).shape(_KEY.entity)
    assert shape is not None
    return shape


def _original(start: dt.datetime, tx_start: dt.datetime) -> ObjectStateKey:
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
    return object_state_key_from_observation(_KEY, TemporalObservation(predecessor=row), _shape())


# --------------------------------------------------------------------------- #
# Owned rows and the insertions they continue.                                #
# --------------------------------------------------------------------------- #
def test_a_row_a_unit_removes_and_reopens_at_one_address_stays_owned() -> None:
    # Removals are retired before openings register, so the row a unit
    # reopened at the address it removed is still the attempt's to revise.
    endpoint = OwnedEndpoint(_KEY.entity, (1,), (Finite(instant=_JUN), PLANNED_INFINITY))
    ownership = WriteOwnership()
    ownership.complete((), Openings(fresh=(endpoint,)))
    ownership.complete((endpoint,), Openings(fresh=(endpoint,)))
    assert ownership.owns(endpoint)


def test_a_stored_insertions_removal_window_is_kept_until_what_it_derives_from_changes() -> None:
    admission, record = _stored(_FEB)
    ownership = _live(admission)
    open_row = _position_endpoint(None)
    ownership.complete((), Openings(continued=(open_row,)))
    window = ownership.removal_window(record)
    assert window == TimeInterval(_FEB, INFINITY)
    assert ownership.removal_window(record) is window
    # Retiring the open row and tagging a bounded one leaves an earlier end.
    bounded = _position_endpoint(_JUN)
    ownership.complete((open_row,), Openings(continued=(bounded,)))
    narrowed = ownership.removal_window(record)
    assert narrowed == TimeInterval(_FEB, _JUN)
    assert narrowed is not window
    # A stored object's further admission keeps its anchor until its batch is
    # drained, and composition cancelling a pending one changes neither tags
    # nor anchor.
    admission.admit(_insert(_APR), confirm_target=_confirmed)
    assert ownership.removal_window(record) is narrowed
    admission.drain_planned()
    moved = ownership.removal_window(record)
    assert moved == TimeInterval(_APR, _JUN)
    _cancel_reinsertion(admission, _MAY)
    assert record.identity is None
    assert ownership.removal_window(record) is moved


def test_an_insertion_keeps_only_its_own_part_of_a_merged_row_and_ends_with_it() -> None:
    admission, record = _stored(_JAN, _APR)
    ownership = _live(admission)
    identity = record.identity
    assert identity is not None
    merged = _position_endpoint(_JUN)
    ownership.complete((), Openings(shared=((merged, (TimeInterval(_JAN, _APR),)),)))
    assert ownership.continues_insertion(merged)
    assert ownership.insertion_coverage(merged, TimeInterval(_JAN, _JUN)) == (
        TimeInterval(_JAN, _APR),
    )
    # Its removal window ends where its own part does, not the merged row.
    assert ownership.removal_window(record) == TimeInterval(_JAN, _APR)
    assert record.identity is identity
    # Revised in place to [April, June), the row holds none of its part.
    ownership.complete((), Openings(fresh=(merged,)))
    assert not ownership.continues_insertion(merged)
    assert ownership.owns(merged)
    assert record.identity is None


def test_a_row_still_holding_part_of_an_insertion_keeps_it_standing() -> None:
    admission, record = _stored(_JAN, _APR)
    ownership = _live(admission)
    identity = record.identity
    merged = _position_endpoint(_JUN)
    ownership.complete((), Openings(shared=((merged, (TimeInterval(_JAN, _APR),)),)))
    narrowed = (TimeInterval(_FEB, _APR),)
    ownership.complete((), Openings(shared=((merged, narrowed),)))
    assert ownership.insertion_coverage(merged, TimeInterval(_FEB, _JUN)) == narrowed
    assert record.identity is identity
    # Whole again once a successor lies inside the part it contributed.
    head = _position_endpoint(_FEB)
    ownership.complete((merged,), Openings(continued=(head,)))
    assert ownership.insertion_coverage(head, TimeInterval(_JAN, _FEB)) == (
        TimeInterval(_JAN, _FEB),
    )
    assert record.identity is identity


def test_an_insertions_part_running_on_without_end_leaves_its_removal_window_open() -> None:
    admission, record = _stored(_JAN, _APR)
    ownership = _live(admission)
    merged = _position_endpoint(None)
    untagged = _position_endpoint(_JAN)
    ownership.complete(
        (), Openings(fresh=(untagged,), shared=((merged, (TimeInterval(_APR, INFINITY),)),))
    )
    assert ownership.insertion_coverage(untagged, TimeInterval(_JAN, _FEB)) == ()
    assert ownership.removal_window(record) == TimeInterval(_JAN, INFINITY)


def _cancel_reinsertion(admission: WriteAdmission, start: dt.datetime) -> None:
    admission.admit(_insert(start), confirm_target=_confirmed)
    identity = admission.insertion_identity(_KEY)
    assert identity is not None
    termination = prepare_wire_write(
        KeyedWriteInstruction("terminate", "WherePosition", ({"id": 1},), start), _POSITION
    )
    assert isinstance(termination, PreparedKeyedWrite)
    admission.admit(InsertionKeyedWrite(termination, identity), confirm_target=_confirmed)


def test_a_row_named_again_after_its_insertion_ended_is_no_longer_tagged() -> None:
    admission, record = _stored(_JAN, _APR)
    ownership = _live(admission)
    row = _position_endpoint(_APR)
    ownership.complete((), Openings(continued=(row,)))
    _cancel_reinsertion(admission, _FEB)
    assert record.identity is None
    assert ownership.continues_insertion(row)
    ownership.complete((), Openings(continued=(row,)))
    assert not ownership.continues_insertion(row)
    assert ownership.owns(row)


# --------------------------------------------------------------------------- #
# What the running flush's units proved for later ones.                       #
# --------------------------------------------------------------------------- #
def test_a_proven_originals_descendants_are_exactly_those_overlapping_the_window() -> None:
    original = _original(_JAN, _T0)
    rows = (
        (_position_endpoint(_FEB), TimeInterval(_JAN, _FEB)),
        (_position_endpoint(_JUN), TimeInterval(_APR, _JUN)),
        (_position_endpoint(None), TimeInterval(_AUG, INFINITY)),
    )
    ownership = WriteOwnership()
    for endpoint, _coverage in rows:
        ownership.complete((), Openings(fresh=(endpoint,)))
    ownership.complete(
        (),
        NO_OPENINGS,
        (
            Derivation(
                original,
                TimeInterval(_JAN, INFINITY),
                None,
                tuple(DerivedRow(endpoint, coverage, coverage) for endpoint, coverage in rows),
            ),
        ),
    )
    # [Feb, Sep) starts where the first row ends: the start index still
    # reaches that row, which the window does not overlap.
    reached = list(ownership.descendants(original, TimeInterval(_FEB, _SEP)))
    assert [(endpoint, descent.valid_time_coverage) for endpoint, descent in reached] == [
        rows[1],
        rows[2],
    ]
    assert all(
        descent.valid_time_coverage is coverage
        for (_e, descent), (_r, coverage) in zip(reached, rows[1:], strict=True)
    )
    assert list(ownership.descendants(original, TimeInterval(_FEB, _APR))) == []
    assert [endpoint for endpoint, _descent in ownership.descendants(original, None)] == [
        endpoint for endpoint, _coverage in rows
    ]


def _merged_derivations(
    first: ObjectStateKey, second: ObjectStateKey, merged: OwnedEndpoint
) -> tuple[Derivation, Derivation]:
    """P1 over [January, June) and P2 over [June, infinity), both amended from
    April through August into one row over [April, August)."""
    whole = TimeInterval(_APR, _AUG)
    return (
        Derivation(
            first,
            TimeInterval(_JAN, _JUN),
            None,
            (
                DerivedRow(
                    _position_endpoint(_APR), TimeInterval(_JAN, _APR), TimeInterval(_JAN, _APR)
                ),
                DerivedRow(merged, whole, TimeInterval(_APR, _JUN)),
            ),
        ),
        Derivation(
            second,
            TimeInterval(_JUN, INFINITY),
            None,
            (
                DerivedRow(merged, whole, TimeInterval(_JUN, _AUG)),
                DerivedRow(
                    _position_endpoint(None),
                    TimeInterval(_AUG, INFINITY),
                    TimeInterval(_AUG, INFINITY),
                ),
            ),
        ),
    )


def _merged_ownership(first: ObjectStateKey, second: ObjectStateKey) -> WriteOwnership:
    ownership = WriteOwnership()
    merged = _position_endpoint(_AUG)
    ownership.complete(
        (),
        Openings(fresh=(_position_endpoint(_APR), merged, _position_endpoint(None))),
        _merged_derivations(first, second, merged),
    )
    return ownership


def test_a_merged_row_descends_from_each_original_over_its_own_part_only() -> None:
    first, second = _original(_JAN, _T0), _original(_JUN, _SECOND_START)
    merged = _position_endpoint(_AUG)
    ownership = _merged_ownership(first, second)
    descent = ownership.descent(merged)
    assert descent is not None
    assert descent.valid_time_coverage == TimeInterval(_APR, _AUG)
    assert descent.contributions == (
        (first, TimeInterval(_APR, _JUN)),
        (second, TimeInterval(_JUN, _AUG)),
    )
    assert (descent.original_at(_FEB), descent.original_at(_APR)) == (None, first)
    assert descent.original_at(dt.datetime(2024, 7, 1, tzinfo=dt.UTC)) == second
    # Only the original whose part a window overlaps reaches the merged row.
    assert [
        endpoint for endpoint, _ in ownership.descendants(first, TimeInterval(_JUN, _SEP))
    ] == []
    assert [
        endpoint for endpoint, _ in ownership.descendants(second, TimeInterval(_FEB, _JUN))
    ] == []
    assert [
        endpoint for endpoint, _ in ownership.descendants(second, TimeInterval(_JUN, _SEP))
    ] == [merged, _position_endpoint(None)]


def test_a_row_derived_from_a_merged_row_inherits_each_original_by_intersection() -> None:
    first, second = _original(_JAN, _T0), _original(_JUN, _SECOND_START)
    merged = _position_endpoint(_AUG)
    ownership = _merged_ownership(first, second)
    # A later unit splits the merged row at May: its head [April, May) came
    # from the first original alone, its tail [May, August) from both.
    revised = _original(_APR, _REVISED_AT)
    head = _position_endpoint(_MAY)
    ownership.complete(
        (),
        Openings(fresh=(head,)),
        (
            Derivation(
                revised,
                TimeInterval(_APR, _AUG),
                merged,
                (
                    DerivedRow(head, TimeInterval(_APR, _MAY), TimeInterval(_APR, _MAY)),
                    DerivedRow(merged, TimeInterval(_MAY, _AUG), TimeInterval(_MAY, _AUG)),
                ),
            ),
        ),
    )
    split_head = ownership.descent(head)
    tail = ownership.descent(merged)
    assert split_head is not None and tail is not None
    assert split_head.contributions == ((first, TimeInterval(_APR, _MAY)),)
    assert tail.contributions == (
        (first, TimeInterval(_MAY, _JUN)),
        (second, TimeInterval(_JUN, _AUG)),
    )
    # The revised row is no proven original of its own.
    assert ownership.proven(revised) is None


def test_a_row_merged_from_one_originals_adjacent_parts_names_it_once() -> None:
    first = _original(_JAN, _T0)
    ownership = WriteOwnership()
    left, right = _position_endpoint(_APR), _position_endpoint(_JUN)
    ownership.complete(
        (),
        Openings(fresh=(left, right)),
        (
            Derivation(
                first,
                TimeInterval(_JAN, _JUN),
                None,
                (
                    DerivedRow(left, TimeInterval(_JAN, _APR), TimeInterval(_JAN, _APR)),
                    DerivedRow(right, TimeInterval(_APR, _JUN), TimeInterval(_APR, _JUN)),
                ),
            ),
        ),
    )
    # A later unit merges both rows the original left, revising the second
    # into [January, June); each part inherits the original over its own
    # Valid Time, and the two parts are one.
    revised_left, revised_right = _original(_JAN, _REVISED_AT), _original(_APR, _REVISED_AT)
    merged = TimeInterval(_JAN, _JUN)
    ownership.complete(
        (left,),
        NO_OPENINGS,
        (
            Derivation(
                revised_left,
                TimeInterval(_JAN, _APR),
                left,
                (DerivedRow(right, merged, TimeInterval(_JAN, _APR)),),
            ),
            Derivation(
                revised_right,
                TimeInterval(_APR, _JUN),
                right,
                (DerivedRow(right, merged, TimeInterval(_APR, _JUN)),),
            ),
        ),
    )
    descent = ownership.descent(right)
    assert descent is not None
    assert descent.contributions == ((first, merged),)


def test_a_part_of_a_row_no_proven_original_held_descends_from_none() -> None:
    first = _original(_JAN, _T0)
    ownership = WriteOwnership()
    merged = _position_endpoint(_JUN)
    # The original contributed [January, April) of the merged row; a gap
    # opened the rest.
    ownership.complete(
        (),
        Openings(fresh=(merged,)),
        (
            Derivation(
                first,
                TimeInterval(_JAN, _APR),
                None,
                (DerivedRow(merged, TimeInterval(_JAN, _JUN), TimeInterval(_JAN, _APR)),),
            ),
        ),
    )
    tail = _position_endpoint(_AUG)
    ownership.complete(
        (),
        Openings(fresh=(tail,)),
        (
            Derivation(
                _original(_JAN, _REVISED_AT),
                TimeInterval(_JAN, _JUN),
                merged,
                (DerivedRow(tail, TimeInterval(_APR, _AUG), TimeInterval(_APR, _JUN)),),
            ),
        ),
    )
    assert ownership.descent(tail) is None


def test_an_original_that_left_no_row_stays_proven_until_its_object_concludes() -> None:
    first = _original(_JAN, _T0)
    ownership = WriteOwnership()
    # Terminated over its whole coverage, the original contributed no row.
    ownership.complete((), NO_OPENINGS, (Derivation(first, TimeInterval(_JAN, _APR), None, ()),))
    assert ownership.proven(first) is not None
    assert list(ownership.descendants(first, TimeInterval(_JAN, INFINITY))) == []
    ownership.complete((), NO_OPENINGS, concludes=first.object)
    assert ownership.proven(first) is None


# --------------------------------------------------------------------------- #
# The fake planning suites read answers as production does.                   #
# --------------------------------------------------------------------------- #
def _fake_like(ownership: WriteOwnership, endpoints: tuple[OwnedEndpoint, ...]) -> OpenedRows:
    descents = {
        endpoint: descent
        for endpoint in endpoints
        if (descent := ownership.descent(endpoint)) is not None
    }
    return OpenedRows(frozenset(endpoints), descents=descents)


def _reached(
    ownership: TemporalWriteOwnership, original: ObjectStateKey, window: TimeInterval | None
) -> list[OwnedEndpoint]:
    return [endpoint for endpoint, _descent in ownership.descendants(original, window)]


@pytest.mark.parametrize(
    "window",
    [None, TimeInterval(_FEB, _SEP), TimeInterval(_JUN, _SEP), TimeInterval(_JAN, _FEB)],
    ids=["unbounded", "both", "later", "earlier"],
)
def test_the_fake_reaches_a_proven_originals_descendants_in_valid_time_order(
    window: TimeInterval | None,
) -> None:
    first, second = _original(_JAN, _T0), _original(_JUN, _SECOND_START)
    production = _merged_ownership(first, second)
    endpoints = (_position_endpoint(_APR), _position_endpoint(_AUG), _position_endpoint(None))
    # Recorded in the reverse of Valid-Time order, which the answers ignore.
    fake = _fake_like(production, tuple(reversed(endpoints)))
    for original in (first, second):
        assert _reached(fake, original, window) == _reached(production, original, window)


def test_the_fake_reaches_no_part_without_valid_time_through_a_bounded_window() -> None:
    log = EntityIdentity("parallax.compatibility", "TransactionLog")
    row = OwnedEndpoint(log, (1,), TRANSACTION_TIME_ENDS)
    original = _original(_JAN, _T0)
    production = WriteOwnership()
    production.complete(
        (),
        Openings(fresh=(row,)),
        (Derivation(original, None, None, (DerivedRow(row, None, None),)),),
    )
    fake = _fake_like(production, (row,))
    for window in (None, TimeInterval(_JAN, _FEB)):
        assert _reached(fake, original, window) == _reached(production, original, window)
    assert _reached(production, original, TimeInterval(_JAN, _FEB)) == []


def test_the_fake_answers_only_the_part_of_an_insertion_a_row_covers() -> None:
    admission, _record = _stored(_JAN, _APR)
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
