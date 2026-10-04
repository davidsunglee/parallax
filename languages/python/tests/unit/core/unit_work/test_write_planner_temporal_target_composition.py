"""How caller-addressed writes of a temporal object join its pending writes and
what the composition binds to, driven at the composition and planner seams
without a database."""

from __future__ import annotations

import datetime as dt
from collections.abc import Sequence
from decimal import Decimal

import pytest

from parallax.core import inheritance, temporal_read
from parallax.core.base import INFINITY
from parallax.core.metamodel import EntityIdentity
from parallax.core.unit_work import (
    KeyedMutation,
    KeyedWrite,
    ObjectKey,
    PlannedClose,
    PlannedInsert,
    PlanningRequest,
    PredecessorRow,
    RetainedObservation,
    TargetWrite,
    TemporalObservation,
    WritePreconditionError,
    buffered_write,
)
from parallax.core.unit_work.instructions import (
    ExpectedTxStart,
    PreparedKeyedWrite,
    TargetMutation,
    prepare_wire_write,
)
from parallax.core.unit_work.materialized import (
    BufferItem,
    ComposedTemporalWrite,
    InsertionKeyedWrite,
    ObservedKeyedWrite,
    TargetKeyedWrite,
    target_write,
)
from parallax.core.unit_work.plan import BoundRange, ExecutionUnit
from parallax.core.unit_work.planned import FAILED_PRECONDITION, UNGATED
from parallax.core.unit_work.planner import TemporalStateKey
from parallax.core.unit_work.retain import InsertionIdentity
from parallax.core.unit_work.write_planner import PendingWrites, compose_writes
from parallax.snapshot.handle import build_write_planner
from tests._support.clock_probes import instant_at
from tests._support.planner_probes import TEST_ACTOR_IDENTITY
from tests.unit._corpus_model_support import corpus_records, formed

_POSITION = formed(corpus_records()["position"])
_FAMILIES = inheritance.view(_POSITION)
_ENTITY = EntityIdentity("parallax.compatibility", "Position")
_OBJECT = ObjectKey(_ENTITY, (("id", 1),))
_T0 = dt.datetime(2023, 12, 1, tzinfo=dt.UTC)
_T1 = dt.datetime(2024, 2, 1, tzinfo=dt.UTC)
_JAN, _MAR, _JUN, _SEP, _DEC = (
    dt.datetime(2024, month, 1, tzinfo=dt.UTC) for month in (1, 3, 6, 9, 12)
)


def _rectangle(
    start: dt.datetime, end: object, value: str, tx_start: dt.datetime = _T0
) -> PredecessorRow:
    return PredecessorRow(
        members={
            "id": 1,
            "acctNum": "A",
            "value": Decimal(value),
            "validStart": start,
            "validEnd": end,
            "txStart": tx_start,
            "txEnd": INFINITY,
        }
    )


def _retained(predecessor: PredecessorRow) -> RetainedObservation:
    observation = TemporalObservation(predecessor=predecessor)
    shape = temporal_read.view(_POSITION).shape(_ENTITY)
    assert shape is not None
    state = TemporalStateKey(_OBJECT, temporal_read.milestone_edge(shape, predecessor, None))
    return RetainedObservation(state, observation, None)


def _target(
    *,
    replaces: bool = False,
    valid_from: dt.datetime = _MAR,
    until: dt.datetime | None = _SEP,
    tx_start: dt.datetime = _T0,
    **members: object,
) -> TargetKeyedWrite:
    mutation: TargetMutation = (
        ("replace" if until is None else "replaceUntil")
        if replaces
        else ("update" if until is None else "updateUntil")
    )
    return target_write(
        prepare_wire_write(
            TargetWrite(
                mutation,
                "Position",
                {"id": 1, **members},
                if_tx_start=tx_start,
                valid_from=valid_from,
                until=until,
            ),
            _POSITION,
        ),
        _FAMILIES,
    )


def _observed(
    mutation: KeyedMutation,
    evidence: RetainedObservation,
    *,
    valid_from: dt.datetime = _MAR,
    until: dt.datetime | None = _SEP,
    **members: object,
) -> ObservedKeyedWrite:
    prepared = prepare_wire_write(
        KeyedWrite(mutation, "Position", ({"id": 1, **members},), valid_from, until), _POSITION
    )
    item = buffered_write(prepared, evidence)
    assert isinstance(item, ObservedKeyedWrite)
    return item


def _pending(*writes: BufferItem) -> PendingWrites:
    pending = PendingWrites(_POSITION)
    for write in writes:
        pending.add(write, _OBJECT)
    return pending


_START = _retained(_rectangle(_JAN, _JUN, "100.00"))
_LATER = _retained(_rectangle(_JUN, INFINITY, "200.00"))
_RESTATED = _retained(_rectangle(_JAN, _JUN, "100.00", tx_start=_T1))


# --------------------------------------------------------------------------- #
# Admission: one window, one starting state, no resurrection.                  #
# --------------------------------------------------------------------------- #
def test_a_target_and_observed_writes_of_its_starting_state_compose_over_one_window() -> None:
    pending = _pending(_observed("updateUntil", _START, acctNum="B"))
    target = _target(value="150.00")
    assert pending.admits_temporal(target, _OBJECT)
    pending.add(target, _OBJECT)
    observed = _observed("updateUntil", _START, value="175.00")
    assert pending.admits_temporal(observed, _OBJECT)
    pending.add(observed, _OBJECT)
    (composed,) = pending.writes()
    assert isinstance(composed, ComposedTemporalWrite)
    assert [contribution.condition for contribution in composed.contributions] == [
        None,
        ExpectedTxStart(_T0),
        None,
    ]
    assert [contribution.claim for contribution in composed.contributions] == [
        _START,
        None,
        _START,
    ]
    (segment,) = composed.transform.segments
    assert dict(segment.assigned or {}) == {"acctNum": "B", "value": Decimal("175.00")}


def test_a_restated_caller_condition_is_kept_once_however_often_it_is_overwritten() -> None:
    pending = _pending(_target(value="1.00"))
    for value in ("2.00", "3.00"):
        pending.add(_target(value=value), _OBJECT)
        pending.add(_target(replaces=True, acctNum="Z", value=value), _OBJECT)
    (composed,) = pending.writes()
    assert isinstance(composed, ComposedTemporalWrite)
    assert [contribution.condition for contribution in composed.contributions] == [
        ExpectedTxStart(_T0)
    ]
    (segment,) = composed.transform.segments
    assert segment.fills
    assert dict(segment.assigned or {}) == {"acctNum": "Z", "value": Decimal("3.00")}


@pytest.mark.parametrize(
    "held",
    [
        pytest.param(lambda: _observed("updateUntil", _RESTATED, value="1.00"), id="another-state"),
        pytest.param(lambda: _target(tx_start=_T1, value="1.00"), id="another-stated-start"),
        pytest.param(
            lambda: _observed("updateUntil", _START, until=_JUN, value="1.00"),
            id="an-unequal-window",
        ),
        pytest.param(
            lambda: _observed("updateUntil", _LATER, valid_from=_SEP, until=_DEC, value="1.00"),
            id="a-disjoint-window",
        ),
        pytest.param(lambda: _observed("terminateUntil", _START), id="a-destruction"),
    ],
)
def test_a_target_beside_a_write_it_cannot_share_a_start_with_is_refused(held: object) -> None:
    pending = _pending(held())  # type: ignore[operator]
    assert not pending.admits_temporal(_target(value="150.00"), _OBJECT)
    assert not pending.admits_temporal(_target(replaces=True, acctNum="Z", value="1.00"), _OBJECT)


def test_a_destruction_of_a_targets_window_supersedes_it_and_nothing_follows() -> None:
    pending = _pending(_target(replaces=True, acctNum="Z", value="1.00"))
    destruction = _observed("terminateUntil", _START)
    assert pending.admits_temporal(destruction, _OBJECT)
    pending.add(destruction, _OBJECT)
    assert not pending.admits_temporal(_observed("updateUntil", _START, value="2.00"), _OBJECT)
    assert not pending.admits_temporal(_target(value="2.00"), _OBJECT)
    (composed,) = pending.writes()
    assert isinstance(composed, ComposedTemporalWrite)
    assert not composed.assigns


def test_a_target_never_joins_a_write_an_insertion_authorized() -> None:
    authored = prepare_wire_write(
        KeyedWrite("updateUntil", "Position", ({"id": 1, "value": "1.00"},), _MAR, _SEP),
        _POSITION,
    )
    assert isinstance(authored, PreparedKeyedWrite)
    pending = _pending(InsertionKeyedWrite(authored, InsertionIdentity(_OBJECT)))
    assert not pending.admits_temporal(_target(value="2.00"), _OBJECT)


def test_an_observed_write_after_a_target_must_state_its_window_and_start() -> None:
    pending = _pending(_target(value="150.00"))
    assert not pending.admits_temporal(
        _observed("updateUntil", _START, until=_JUN, value="1.00"), _OBJECT
    )
    assert not pending.admits_temporal(_observed("updateUntil", _RESTATED, value="1.00"), _OBJECT)
    assert pending.admits_temporal(_observed("updateUntil", _START, value="1.00"), _OBJECT)


def test_a_target_meeting_any_earlier_unequal_contribution_is_refused() -> None:
    # Pure observed writes compose over unequal windows; a target joining them
    # must agree with every one, not only the latest.
    earlier = _pending(
        _observed("update", _START, valid_from=_JAN, until=None, value="1.00"),
        _observed("updateUntil", _START, value="2.00"),
    )
    assert not earlier.admits_temporal(_target(value="3.00"), _OBJECT)
    target_first = _pending(_target(value="3.00"), _observed("updateUntil", _START, value="2.00"))
    assert not target_first.admits_temporal(
        _observed("update", _START, valid_from=_JAN, until=None, value="1.00"), _OBJECT
    )


# --------------------------------------------------------------------------- #
# Binding: the caller's start, replacement extent, and destruction.            #
# --------------------------------------------------------------------------- #
def _deferred_unit(*writes: BufferItem, concurrency: str = "optimistic") -> ExecutionUnit:
    plan = (
        build_write_planner(_POSITION)
        .finalize(
            PlanningRequest(
                actor_identity=TEST_ACTOR_IDENTITY,
                transaction_instant=instant_at("2024-10-01T00:00:00+00:00"),
                concurrency=concurrency,  # type: ignore[arg-type]
                buffered_writes=compose_writes(_POSITION, list(writes)),
            )
        )
        .plan
    )
    (unit,) = plan.units
    assert unit.deferred is not None
    return unit


def _bound(unit: ExecutionUnit, rows: Sequence[PredecessorRow]) -> BoundRange:
    assert unit.deferred is not None
    return unit.deferred.bind(rows)


def _windows(bound: BoundRange) -> list[tuple[object, object, object]]:
    windows: list[tuple[object, object, object]] = []
    for step in bound.steps:
        if isinstance(step, PlannedInsert):
            (entry,) = step.entries
            cells = {identity.name: value for identity, value in entry.row.attributes.items()}
            windows.append((cells["validStart"], cells["validEnd"], cells["value"]))
    return windows


def test_a_target_range_reads_its_window_and_gates_its_start_on_the_callers_revision() -> None:
    unit = _deferred_unit(_target(value="150.00"))
    assert unit.deferred is not None
    acquisition = unit.deferred.acquisition
    assert (acquisition.valid_from, acquisition.until, acquisition.locking) == (_MAR, _SEP, False)
    bound = _bound(unit, [_START.evidence.predecessor, _LATER.evidence.predecessor])  # type: ignore[union-attr]
    first, second = (step for step in bound.steps if isinstance(step, PlannedClose))
    assert first.affected_rows.on_shortfall == FAILED_PRECONDITION
    assert second.affected_rows.on_shortfall != FAILED_PRECONDITION
    assert _windows(bound) == [
        (_JAN, _MAR, Decimal("100.00")),
        (_MAR, _JUN, Decimal("150.00")),
        (_JUN, _SEP, Decimal("150.00")),
        (_SEP, INFINITY, Decimal("200.00")),
    ]


@pytest.mark.parametrize(
    "coverage",
    [
        pytest.param([], id="no-coverage"),
        pytest.param([_rectangle(_JUN, INFINITY, "200.00")], id="a-gap-at-the-start"),
        pytest.param([_rectangle(_JAN, _JUN, "100.00", tx_start=_T1)], id="another-revision"),
    ],
)
def test_a_target_whose_start_does_not_stand_at_its_callers_revision_binds_nothing(
    coverage: list[PredecessorRow],
) -> None:
    unit = _deferred_unit(_target(replaces=True, acctNum="Z", value="1.00"))
    with pytest.raises(WritePreconditionError) as refused:
        _bound(unit, coverage)
    assert (dict(refused.value.key), refused.value.expected) == ({"id": 1}, _T0)


def test_a_replacement_fills_the_gaps_of_its_extent_once_and_a_destruction_fills_none() -> None:
    coverage = [_rectangle(_JAN, _MAR + dt.timedelta(days=30), "100.00")]
    coverage.append(_rectangle(_JUN, _DEC, "200.00"))
    replaced = _bound(
        _deferred_unit(_target(replaces=True, until=None, acctNum="Z", value="9.00")),
        coverage,
    )
    assert _windows(replaced) == [
        (_JAN, _MAR, Decimal("100.00")),
        (_MAR, _MAR + dt.timedelta(days=30), Decimal("9.00")),
        (_JUN, _DEC, Decimal("9.00")),
        (_MAR + dt.timedelta(days=30), _JUN, Decimal("9.00")),
        (_DEC, "infinity", Decimal("9.00")),
    ]
    # The destruction observed [January, June), so the flush reads only the
    # coverage from June on.
    destroyed = _bound(
        _deferred_unit(
            _target(replaces=True, until=None, acctNum="Z", value="9.00"),
            _observed("terminate", _START, until=None),
        ),
        [_rectangle(_JUN, _DEC, "200.00")],
    )
    assert _windows(destroyed) == [(_JAN, _MAR, Decimal("100.00"))]
    first = next(step for step in destroyed.steps if isinstance(step, PlannedClose))
    assert first.affected_rows.on_shortfall == FAILED_PRECONDITION


def test_a_patch_after_a_replacement_keeps_its_extent_and_overlays_its_gaps() -> None:
    coverage = [_rectangle(_JAN, _JUN, "100.00")]
    bound = _bound(
        _deferred_unit(
            _target(replaces=True, acctNum="Z", value="9.00"),
            _observed("updateUntil", _START, value="7.00"),
            _target(acctNum="Y"),
        ),
        coverage,
    )
    assert _windows(bound) == [
        (_JAN, _MAR, Decimal("100.00")),
        (_MAR, _JUN, Decimal("7.00")),
        (_JUN, _SEP, Decimal("7.00")),
    ]
    opened = [
        {identity.name: value for identity, value in step.entries[0].row.attributes.items()}
        for step in bound.steps
        if isinstance(step, PlannedInsert)
    ]
    assert [cells["acctNum"] for cells in opened] == ["A", "Y", "Y"]


def test_a_locking_target_range_reads_its_coverage_under_the_shared_lock_ungated() -> None:
    unit = _deferred_unit(_target(value="150.00"), concurrency="locking")
    assert unit.deferred is not None
    assert unit.deferred.acquisition.locking
    bound = _bound(unit, [_START.evidence.predecessor])  # type: ignore[union-attr]
    close = next(step for step in bound.steps if isinstance(step, PlannedClose))
    assert close.concurrency == UNGATED
