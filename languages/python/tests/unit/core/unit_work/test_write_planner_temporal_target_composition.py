"""How caller-addressed writes of a temporal object join its pending writes and
what the composition binds to, driven at the composition and planner seams
without a database: exact-window composition, disjoint operations, the
compositions an ordering barrier keeps apart, and what a composition after one
binds to."""

from __future__ import annotations

import datetime as dt
from collections.abc import Callable, Sequence
from decimal import Decimal
from typing import Literal

import pytest

from parallax.core import inheritance, temporal_read
from parallax.core import predicate as predicate_algebra
from parallax.core.base import INFINITY, TemporalBound
from parallax.core.metamodel import EntityIdentity
from parallax.core.temporal_read import TimeInterval
from parallax.core.unit_work import (
    CardinalityCorruptionError,
    KeyedMutation,
    KeyedWrite,
    OptimisticLockConflictError,
    PlanningRequest,
    PredicateSelection,
    PredicateWrite,
    RetainedObservation,
    StaleWriteError,
    TargetWrite,
    WriteAssignment,
    WritePreconditionError,
    buffered_write,
)
from parallax.core.unit_work.instructions import (
    ExpectedTxStart,
    PreparedKeyedWrite,
    PreparedPredicateWrite,
    TargetMutation,
    prepare_wire_write,
)
from parallax.core.unit_work.materialized import (
    BufferItem,
    ChainedTemporalWrite,
    ComposedTemporalWrite,
    InsertionKeyedWrite,
    ObservedKeyedWrite,
    TargetKeyedWrite,
    chained,
    target_write,
)
from parallax.core.unit_work.retain import InsertionIdentity
from parallax.core.unit_work.write_planner import PendingWrites, compose_writes
from parallax.core.write_plan import (
    ObjectKey,
    PlannedClose,
    PlannedInsert,
    PredecessorRow,
    TemporalObservation,
)
from parallax.core.write_plan.keys import TemporalStateKey
from parallax.core.write_plan.plan import (
    NO_OWNERSHIP,
    OPEN_BITEMPORAL_ENDS,
    BoundRange,
    Derivation,
    Descent,
    ExecutionUnit,
    OwnedEndpoint,
    Ownership,
)
from parallax.core.write_plan.steps import (
    FAILED_PRECONDITION,
    UNGATED,
    Finite,
    PlannedTemporalRevision,
)
from parallax.core.write_plan.steps import INFINITY as OPEN_END
from parallax.snapshot.handle import build_write_planner
from tests._support.clock_probes import instant_at
from tests._support.planner_probes import TEST_ACTOR_IDENTITY
from tests.unit._corpus_model_support import corpus_records, formed
from tests.unit.core.unit_work._ownership_support import OpenedRows

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


def test_a_range_its_observations_leave_uncovered_reads_only_the_uncovered_suffix() -> None:
    observed = _observed(
        "updateUntil",
        _retained(_rectangle(_JAN, _JUN, "100.00")),
        valid_from=_MAR,
        until=_SEP,
        acctNum="O",
    )
    unit = _deferred_unit(observed)
    assert unit.deferred is not None
    window = unit.deferred.acquisition.valid_time_window
    assert window == TimeInterval(_JUN, _SEP)
    prepared = observed.instruction.valid_time_window
    assert prepared is not None and window is not None
    assert window.end is prepared.end


def test_a_lone_target_range_reads_through_the_very_window_its_caller_prepared() -> None:
    target = _target(value="150.00")
    unit = _deferred_unit(target)
    assert unit.deferred is not None
    assert unit.deferred.acquisition.valid_time_window is target.instruction.valid_time_window


def test_a_target_range_reads_its_window_and_gates_its_start_on_the_callers_revision() -> None:
    unit = _deferred_unit(_target(value="150.00"))
    assert unit.deferred is not None
    acquisition = unit.deferred.acquisition
    assert (acquisition.valid_time_window, acquisition.locking) == (TimeInterval(_MAR, _SEP), False)
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
        (_DEC, INFINITY, Decimal("9.00")),
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


# --------------------------------------------------------------------------- #
# Disjoint operations: separate windows of one object, each its own condition. #
# --------------------------------------------------------------------------- #
_FEB, _APR, _MAY, _JUL, _AUG, _OCT = (
    dt.datetime(2024, month, 1, tzinfo=dt.UTC) for month in (2, 4, 5, 7, 8, 10)
)
_T = dt.datetime(2024, 10, 1, tzinfo=dt.UTC)
_WHOLE = _retained(_rectangle(_JAN, INFINITY, "100.00"))

type _Write = Callable[[dt.datetime, dt.datetime], BufferItem]

_KINDS: dict[str, _Write] = {
    "P": lambda start, until: _target(valid_from=start, until=until, value="150.00"),
    "R": lambda start, until: _target(
        replaces=True, valid_from=start, until=until, acctNum="Z", value="9.00"
    ),
    "O": lambda start, until: _observed(
        "updateUntil", _WHOLE, valid_from=start, until=until, acctNum="O"
    ),
    "D": lambda start, until: _observed("terminateUntil", _WHOLE, valid_from=start, until=until),
}
_PAIRS = ["P-P", "P-R", "R-P", "R-R", "P-O", "O-P", "R-O", "O-R", "P-D", "D-P", "R-D", "D-R"]
_GEOMETRIES = {
    "separated": ((_FEB, _APR), (_JUN, _AUG)),
    "adjacent": ((_FEB, _APR), (_APR, _JUN)),
}


@pytest.mark.parametrize("windows", ["earlier-first", "later-first"])
@pytest.mark.parametrize("geometry", list(_GEOMETRIES))
@pytest.mark.parametrize("pair", _PAIRS)
def test_writes_over_disjoint_windows_of_one_original_stay_separate_operations(
    pair: str, geometry: str, windows: str
) -> None:
    first_window, second_window = _GEOMETRIES[geometry]
    if windows == "later-first":
        first_window, second_window = second_window, first_window
    first_kind, second_kind = pair.split("-")
    first = _KINDS[first_kind](*first_window)
    second = _KINDS[second_kind](*second_window)
    pending = _pending(first)
    assert pending.admits_temporal(second, _OBJECT)  # type: ignore[arg-type]
    pending.add(second, _OBJECT)
    (composed,) = pending.writes()
    assert isinstance(composed, ComposedTemporalWrite)
    # Each operation keeps its own window and its own condition: a caller's
    # stated start, or the rectangle its source observed.
    assert [c.valid_time_window for c in composed.contributions] == [
        TimeInterval(*first_window),
        TimeInterval(*second_window),
    ]
    assert [c.condition is not None for c in composed.contributions] == [
        kind in "PR" for kind in (first_kind, second_kind)
    ]
    destroyed = {
        segment.valid_time_window
        for segment in composed.transform.segments
        if segment.assigned is None
    }
    assert destroyed == {
        TimeInterval(*window)
        for kind, window in ((first_kind, first_window), (second_kind, second_window))
        if kind == "D"
    }


@pytest.mark.parametrize(
    ("held", "arriving"),
    [
        pytest.param(("P", _FEB, _JUN), ("P", _APR, _AUG), id="P-P"),
        pytest.param(("P", _FEB, _JUN), ("O", _APR, _AUG), id="P-O"),
        pytest.param(("O", _APR, _AUG), ("P", _FEB, _JUN), id="O-P"),
        pytest.param(("R", _FEB, _JUN), ("D", _APR, _AUG), id="R-D"),
        pytest.param(("D", _APR, _AUG), ("R", _FEB, _JUN), id="D-R"),
        pytest.param(("P", _FEB, _AUG), ("R", _APR, _JUN), id="P-R-inside"),
    ],
)
def test_a_target_overlapping_another_write_unequally_is_refused(
    held: tuple[str, dt.datetime, dt.datetime], arriving: tuple[str, dt.datetime, dt.datetime]
) -> None:
    kind, start, until = held
    pending = _pending(_KINDS[kind](start, until))
    kind, start, until = arriving
    assert not pending.admits_temporal(_KINDS[kind](start, until), _OBJECT)  # type: ignore[arg-type]


def test_an_unbounded_window_overlaps_every_window_after_its_start() -> None:
    unbounded = _pending(_target(valid_from=_MAR, until=None, value="150.00"))
    assert not unbounded.admits_temporal(
        _observed("updateUntil", _WHOLE, valid_from=_SEP, until=_OCT, acctNum="O"), _OBJECT
    )
    # A different stored rectangle at the later start does not make it disjoint.
    assert not unbounded.admits_temporal(
        _target(valid_from=_SEP, until=_OCT, tx_start=_T1, value="1.00"), _OBJECT
    )
    before = _pending(_observed("updateUntil", _WHOLE, valid_from=_FEB, until=_MAR, acctNum="O"))
    assert before.admits_temporal(_target(valid_from=_MAR, until=None, value="150.00"), _OBJECT)


def test_a_write_disjoint_from_the_latest_but_overlapping_an_earlier_one_is_refused() -> None:
    # Two observed writes may overlap each other; a target disjoint from both
    # joins them, and a later target is judged against every one of them.
    pending = _pending(
        _observed("updateUntil", _WHOLE, valid_from=_MAR, until=_JUN, acctNum="A1"),
        _observed("updateUntil", _WHOLE, valid_from=_APR, until=_AUG, acctNum="A2"),
    )
    disjoint = _target(valid_from=_SEP, until=_OCT, value="150.00")
    assert pending.admits_temporal(disjoint, _OBJECT)
    pending.add(disjoint, _OBJECT)
    assert not pending.admits_temporal(_target(valid_from=_JUL, until=_SEP, value="1.00"), _OBJECT)
    assert not pending.admits_temporal(
        _observed("terminateUntil", _WHOLE, valid_from=_MAY, until=_SEP), _OBJECT
    )


@pytest.mark.parametrize("order", ["observed-first", "target-first"])
def test_a_target_starting_inside_an_observed_rectangle_must_state_its_revision(
    order: str,
) -> None:
    observed = _observed("updateUntil", _WHOLE, valid_from=_FEB, until=_APR, acctNum="O")
    for tx_start, admitted in ((_T0, True), (_T1, False)):
        target = _target(valid_from=_JUN, until=_AUG, tx_start=tx_start, value="150.00")
        held, arriving = (observed, target) if order == "observed-first" else (target, observed)
        assert _pending(held).admits_temporal(arriving, _OBJECT) is admitted


def test_a_shared_token_names_whatever_rectangle_holds_each_start() -> None:
    # The source observed only [January, June); a caller stating the same
    # Transaction-Time start for September names whichever rectangle holds it.
    pending = _pending(_observed("updateUntil", _START, valid_from=_FEB, until=_APR, acctNum="O"))
    assert pending.admits_temporal(_target(valid_from=_SEP, until=_OCT, value="1.00"), _OBJECT)
    assert pending.admits_temporal(
        _target(valid_from=_SEP, until=_OCT, tx_start=_T1, value="1.00"), _OBJECT
    )


# --------------------------------------------------------------------------- #
# Ordering barriers: an object's writes on each side compose apart.           #
# --------------------------------------------------------------------------- #
_WALLET = formed(corpus_records()["wallet"])


def _barrier() -> PreparedPredicateWrite:
    prepared = prepare_wire_write(
        PredicateWrite(
            "update",
            PredicateSelection("Wallet", predicate_algebra.Comparison("eq", "Wallet.id", 1)),
            assignments=(WriteAssignment("Wallet.owner", "Q"),),
        ),
        _WALLET,
    )
    assert isinstance(prepared, PreparedPredicateWrite)
    return prepared


def test_a_readless_predicate_write_separates_an_objects_writes_into_chained_compositions() -> None:
    pending = _pending(
        _target(valid_from=_FEB, until=_APR, value="1.00"),
        _barrier(),
        _target(valid_from=_JUN, until=_AUG, value="2.00"),
        _observed("updateUntil", _WHOLE, valid_from=_SEP, until=_OCT, acctNum="O"),
        _barrier(),
        _observed("terminateUntil", _WHOLE, valid_from=_OCT, until=_DEC),
    )
    first, _q1, middle, _q2, last = pending.writes()
    chain = [
        (type(write).__name__, write.leads, write.follows, len(write.contributions))
        for write in (first, middle, last)
        if isinstance(write, ChainedTemporalWrite)
    ]
    assert chain == [
        ("ChainedTemporalWrite", True, False, 1),
        ("ChainedTemporalWrite", True, True, 2),
        ("ChainedTemporalWrite", False, True, 1),
    ]


def test_admission_across_a_barrier_judges_every_write_of_the_object() -> None:
    pending = _pending(_target(valid_from=_FEB, until=_APR, value="1.00"), _barrier())
    # Unequal overlap with the write before the barrier is refused there too.
    assert not pending.admits_temporal(
        _observed("updateUntil", _WHOLE, valid_from=_MAR, until=_JUN, acctNum="O"), _OBJECT
    )
    # One window and one start compose, though they execute as two units.
    exact = _observed("updateUntil", _WHOLE, valid_from=_FEB, until=_APR, acctNum="O")
    assert pending.admits_temporal(exact, _OBJECT)
    pending.add(exact, _OBJECT)
    first, _barrier_write, second = pending.writes()
    assert isinstance(first, ChainedTemporalWrite) and first.leads
    assert isinstance(second, ChainedTemporalWrite) and second.follows


def test_a_pure_observed_composition_after_a_barrier_follows_the_earlier_one() -> None:
    pending = _pending(
        _observed("updateUntil", _WHOLE, valid_from=_MAR, until=_JUN, acctNum="A"),
        _barrier(),
        _observed("updateUntil", _WHOLE, valid_from=_APR, until=_AUG, acctNum="B"),
    )
    first, _barrier_write, second = pending.writes()
    assert isinstance(first, ChainedTemporalWrite) and (first.leads, first.follows) == (True, False)
    assert isinstance(second, ChainedTemporalWrite) and (second.leads, second.follows) == (
        False,
        True,
    )


# --------------------------------------------------------------------------- #
# Binding disjoint operations: one transform per original, a guard per start.  #
# --------------------------------------------------------------------------- #
def test_disjoint_targets_over_one_original_transform_it_once_under_one_guard() -> None:
    unit = _deferred_unit(
        _target(valid_from=_FEB, until=_APR, value="150.00"),
        _target(valid_from=_JUN, until=_AUG, value="175.00"),
    )
    assert unit.deferred is not None
    assert unit.deferred.acquisition.valid_time_window == TimeInterval(_FEB, _AUG)
    bound = _bound(unit, [_WHOLE.evidence.predecessor])  # type: ignore[union-attr]
    (close,) = (step for step in bound.steps if isinstance(step, PlannedClose))
    assert close.affected_rows.on_shortfall == FAILED_PRECONDITION
    assert _windows(bound) == [
        (_JAN, _FEB, Decimal("100.00")),
        (_FEB, _APR, Decimal("150.00")),
        (_APR, _JUN, Decimal("100.00")),
        (_JUN, _AUG, Decimal("175.00")),
        (_AUG, INFINITY, Decimal("100.00")),
    ]


def test_disjoint_targets_over_distinct_originals_guard_each_start_in_authored_order() -> None:
    unit = _deferred_unit(
        _target(valid_from=_SEP, until=_OCT, tx_start=_T1, value="175.00"),
        _target(valid_from=_FEB, until=_APR, value="150.00"),
    )
    later = _rectangle(_JUN, INFINITY, "200.00", tx_start=_T1)
    bound = _bound(unit, [_START.evidence.predecessor, later])  # type: ignore[union-attr]
    closes = [step for step in bound.steps if isinstance(step, PlannedClose)]
    # The first-authored start's guard runs first, whatever its Valid Time.
    assert [close.concurrency.observed_start for close in closes] == [_T1, _T0]  # type: ignore[union-attr]
    assert [close.affected_rows.on_shortfall for close in closes] == [FAILED_PRECONDITION] * 2


def test_a_disjoint_operations_stale_start_fails_as_its_own_callers_precondition() -> None:
    unit = _deferred_unit(
        _target(valid_from=_FEB, until=_APR, value="150.00"),
        _target(valid_from=_JUN, until=_AUG, tx_start=_T1, value="175.00"),
    )
    with pytest.raises(WritePreconditionError) as refused:
        _bound(unit, [_WHOLE.evidence.predecessor])  # type: ignore[union-attr]
    assert refused.value.expected == _T1


def test_two_current_rows_at_any_operations_start_are_corruption() -> None:
    unit = _deferred_unit(
        _target(valid_from=_FEB, until=_APR, value="150.00"),
        _target(valid_from=_JUN, until=_AUG, value="175.00"),
    )
    overlapping = [_rectangle(_JAN, _JUN, "100.00"), _rectangle(_MAY, _DEC, "1.00", tx_start=_T1)]
    overlapping.append(_rectangle(_JUN, _SEP, "2.00", tx_start=_T1))
    with pytest.raises(CardinalityCorruptionError):
        _bound(unit, overlapping)


def test_a_replacement_fills_only_its_own_window_beside_a_disjoint_destruction() -> None:
    later = _rectangle(_APR, INFINITY, "200.00", tx_start=_T1)
    unit = _deferred_unit(
        _target(replaces=True, valid_from=_FEB, until=_JUN, acctNum="Z", value="9.00"),
        _observed("terminateUntil", _retained(later), valid_from=_JUL, until=_SEP),
    )
    gapped = [_rectangle(_JAN, _MAR, "100.00"), later]
    bound = _bound(unit, gapped)
    assert sorted(_windows(bound), key=lambda window: window[0]) == [  # type: ignore[arg-type, return-value]
        (_JAN, _FEB, Decimal("100.00")),
        (_FEB, _MAR, Decimal("9.00")),
        (_MAR, _APR, Decimal("9.00")),
        (_APR, _JUN, Decimal("9.00")),
        (_JUN, _JUL, Decimal("200.00")),
        (_SEP, INFINITY, Decimal("200.00")),
    ]


# --------------------------------------------------------------------------- #
# Continuation across a barrier: what an earlier unit of the flush proved.     #
# --------------------------------------------------------------------------- #
def _chained_unit(
    *writes: BufferItem,
    ownership: Ownership = NO_OWNERSHIP,
    leads: bool = False,
    follows: bool = True,
    concurrency: str = "optimistic",
) -> ExecutionUnit:
    (composed,) = compose_writes(_POSITION, list(writes))
    assert isinstance(composed, ComposedTemporalWrite | TargetKeyedWrite | ObservedKeyedWrite)
    plan = (
        build_write_planner(_POSITION)
        .finalize(
            PlanningRequest(
                actor_identity=TEST_ACTOR_IDENTITY,
                transaction_instant=instant_at("2024-10-01T00:00:00+00:00"),
                concurrency=concurrency,  # type: ignore[arg-type]
                buffered_writes=(chained(composed, "id", leads=leads, follows=follows),),
                ownership=ownership,
            )
        )
        .plan
    )
    (unit,) = plan.units
    return unit


def _endpoint(end: object) -> OwnedEndpoint:
    ends = OPEN_BITEMPORAL_ENDS if end is INFINITY else (Finite(instant=end), OPEN_END)
    return OwnedEndpoint(_ENTITY, (1,), ends)


# What an earlier unit's patch of [February, April) left of [January, infinity).
_LEFT = ((_JAN, _FEB), (_FEB, _APR), (_APR, INFINITY))


def _lineage(
    left: tuple[tuple[dt.datetime, dt.datetime | Literal[TemporalBound.INFINITY]], ...],
) -> tuple[tuple[OwnedEndpoint, TimeInterval], ...]:
    return tuple((_endpoint(end), TimeInterval(start, end)) for start, end in left)


def _proven(original: RetainedObservation = _WHOLE) -> OpenedRows:
    rows = _lineage(_LEFT)
    return OpenedRows(
        endpoints=frozenset(endpoint for endpoint, _coverage in rows),
        proofs={original.key: Derivation(original.key, TimeInterval(_JAN, INFINITY), None, rows)},
        descents={endpoint: Descent(coverage, original.key) for endpoint, coverage in rows},
    )


def _opened(start: dt.datetime, value: str = "100.00", **cells: object) -> PredecessorRow:
    row = _rectangle(start, INFINITY, value, tx_start=_T)
    return PredecessorRow(members={**row.members, **cells}) if cells else row


def test_a_following_range_reads_its_whole_window_and_discharges_a_proven_start() -> None:
    unit = _chained_unit(_target(valid_from=_JUN, until=_AUG, value="175.00"), ownership=_proven())
    assert unit.deferred is not None
    assert unit.deferred.acquisition.valid_time_window == TimeInterval(_JUN, _AUG)
    bound = _bound(unit, [_opened(_APR)])
    # The start now stands at the row the earlier unit derived from the
    # original the caller stated; that row is the attempt's own, so it is
    # revised in place rather than closed, and nothing gates on the caller.
    assert not any(isinstance(step, PlannedClose) for step in bound.steps)
    (revision,) = (step for step in bound.steps if isinstance(step, PlannedTemporalRevision))
    assert revision.affected_rows.on_shortfall != FAILED_PRECONDITION
    assert _windows(bound) == [
        (_APR, _JUN, Decimal("100.00")),
        (_JUN, _AUG, Decimal("175.00")),
    ]


@pytest.mark.parametrize(
    ("ownership", "coverage"),
    [
        pytest.param(OpenedRows(frozenset({_endpoint(INFINITY)})), [_opened(_APR)], id="no-proof"),
        pytest.param(_proven(), [_opened(_APR, txStart=_T + dt.timedelta(days=1))], id="restamped"),
        pytest.param(_proven(), [_opened(_MAY)], id="moved-start"),
        pytest.param(_proven(), [], id="removed"),
    ],
)
def test_a_following_start_no_intact_proof_carries_is_the_callers_precondition(
    ownership: OpenedRows, coverage: list[PredecessorRow]
) -> None:
    unit = _chained_unit(_target(valid_from=_JUN, until=_AUG, value="175.00"), ownership=ownership)
    with pytest.raises(WritePreconditionError) as refused:
        _bound(unit, coverage)
    assert refused.value.expected == _T0


def test_a_following_observed_write_binds_to_the_values_the_earlier_unit_left() -> None:
    unit = _chained_unit(
        _observed("updateUntil", _WHOLE, valid_from=_JUN, until=_AUG, acctNum="O"),
        ownership=_proven(),
    )
    bound = _bound(unit, [_opened(_APR, "150.00")])
    opened = [
        {identity.name: value for identity, value in step.entries[0].row.attributes.items()}
        for step in bound.steps
        if isinstance(step, PlannedInsert)
    ]
    # The unassigned value is the current row's, never the observed original's.
    assert [(cells["acctNum"], cells["value"]) for cells in opened] == [
        ("A", Decimal("150.00")),
        ("O", Decimal("150.00")),
    ]


@pytest.mark.parametrize(
    ("concurrency", "error"),
    [("optimistic", OptimisticLockConflictError), ("locking", StaleWriteError)],
)
def test_a_following_observed_original_neither_standing_nor_proven_fails_as_its_own_shortfall(
    concurrency: str, error: type[Exception]
) -> None:
    unit = _chained_unit(
        _observed("updateUntil", _WHOLE, valid_from=_JUN, until=_AUG, acctNum="O"),
        ownership=OpenedRows(frozenset()),
        concurrency=concurrency,
    )
    with pytest.raises(error):
        _bound(unit, [_rectangle(_APR, INFINITY, "100.00", tx_start=_T1)])


def test_a_following_observed_original_still_standing_binds_as_any_original() -> None:
    unit = _chained_unit(
        _observed("updateUntil", _WHOLE, valid_from=_JUN, until=_AUG, acctNum="O"),
        ownership=OpenedRows(frozenset()),
    )
    bound = _bound(unit, [_WHOLE.evidence.predecessor])  # type: ignore[union-attr]
    (close,) = (step for step in bound.steps if isinstance(step, PlannedClose))
    assert close.concurrency.observed_start == _T0  # type: ignore[union-attr]


def test_a_following_callers_precondition_outranks_a_lost_observation() -> None:
    unit = _chained_unit(
        _observed("updateUntil", _WHOLE, valid_from=_FEB, until=_APR, acctNum="O"),
        _target(valid_from=_JUN, until=_AUG, value="175.00"),
        ownership=OpenedRows(frozenset()),
    )
    with pytest.raises(WritePreconditionError):
        _bound(unit, [_rectangle(_JAN, INFINITY, "100.00", tx_start=_T1)])


def test_a_leading_range_records_what_it_derived_from_each_original() -> None:
    unit = _chained_unit(
        _target(valid_from=_FEB, until=_APR, value="150.00"), leads=True, follows=False
    )
    bound = _bound(unit, [_WHOLE.evidence.predecessor])  # type: ignore[union-attr]
    (derivation,) = bound.derived
    assert derivation.original == _WHOLE.key
    assert derivation.owned is None
    assert derivation.rows == _lineage(_LEFT)
    assert derivation.valid_time_coverage == TimeInterval(_JAN, INFINITY)
    plain = _deferred_unit(_target(valid_from=_FEB, until=_APR, value="150.00"))
    assert _bound(plain, [_WHOLE.evidence.predecessor]).derived == ()  # type: ignore[union-attr]


def test_a_following_start_untouched_at_its_stated_start_is_judged_as_usual() -> None:
    later = _rectangle(_JUN, INFINITY, "200.00", tx_start=_T1)
    unit = _chained_unit(
        _target(valid_from=_JUL, until=_AUG, tx_start=_T1, value="175.00"),
        ownership=OpenedRows(frozenset()),
    )
    bound = _bound(unit, [later])
    (close,) = (step for step in bound.steps if isinstance(step, PlannedClose))
    assert close.affected_rows.on_shortfall == FAILED_PRECONDITION


def _unproven_descent() -> OpenedRows:
    proven = _proven()
    return OpenedRows(endpoints=proven.endpoints, descents=proven.descents)


def _short_proof() -> OpenedRows:
    rows = _lineage(_LEFT)
    return OpenedRows(
        endpoints=frozenset(endpoint for endpoint, _coverage in rows),
        proofs={_WHOLE.key: Derivation(_WHOLE.key, TimeInterval(_JAN, _MAY), None, rows)},
        descents={endpoint: Descent(coverage, _WHOLE.key) for endpoint, coverage in rows},
    )


@pytest.mark.parametrize(
    ("ownership", "tx_start"),
    [
        pytest.param(_unproven_descent(), _T0, id="a-descent-nothing-proved"),
        pytest.param(_proven(), _T1, id="another-revision-than-the-original"),
        pytest.param(_short_proof(), _T0, id="a-start-outside-the-original"),
    ],
)
def test_a_following_start_whose_proof_names_another_state_is_the_callers_precondition(
    ownership: OpenedRows, tx_start: dt.datetime
) -> None:
    unit = _chained_unit(
        _target(valid_from=_JUN, until=_AUG, tx_start=tx_start, value="175.00"),
        ownership=ownership,
    )
    with pytest.raises(WritePreconditionError):
        _bound(unit, [_opened(_APR)])


def test_a_following_range_fails_where_another_row_derived_from_its_original_is_gone() -> None:
    left = ((_JAN, _FEB), (_FEB, _APR), (_APR, _JUL), (_JUL, INFINITY))
    rows = _lineage(left)
    ownership = OpenedRows(
        endpoints=frozenset(endpoint for endpoint, _coverage in rows),
        proofs={_WHOLE.key: Derivation(_WHOLE.key, TimeInterval(_JAN, INFINITY), None, rows)},
        descents={endpoint: Descent(coverage, _WHOLE.key) for endpoint, coverage in rows},
    )
    unit = _chained_unit(_target(valid_from=_JUN, until=_AUG, value="175.00"), ownership=ownership)
    # The start stands, but [July, infinity), derived from the same original
    # inside the window, does not.
    with pytest.raises(WritePreconditionError):
        _bound(unit, [PredecessorRow(members={**_opened(_APR).members, "validEnd": _JUL})])


def test_a_leading_range_records_an_overlapped_observation_it_only_validated() -> None:
    earlier = _retained(_rectangle(_JAN, _JUN, "100.00"))
    later = _retained(_rectangle(_MAR, INFINITY, "300.00", tx_start=_T1))
    unit = _chained_unit(
        _observed("updateUntil", earlier, valid_from=_FEB, until=_APR, acctNum="E"),
        _observed("updateUntil", later, valid_from=_MAY, until=_JUL, acctNum="L"),
        leads=True,
        follows=False,
    )
    validated, transformed = _bound(unit, [later.evidence.predecessor]).derived  # type: ignore[union-attr]
    assert (validated.original, validated.rows) == (earlier.key, ())
    assert transformed.original == later.key


def test_a_callers_start_is_guarded_ahead_of_an_overlapped_observation_it_validates() -> None:
    earlier = _retained(_rectangle(_JAN, _JUN, "100.00"))
    later = _retained(_rectangle(_MAR, INFINITY, "300.00", tx_start=_T1))
    unit = _deferred_unit(
        _observed("updateUntil", earlier, valid_from=_FEB, until=_MAR, acctNum="E"),
        _observed("updateUntil", later, valid_from=_MAY, until=_JUL, acctNum="L"),
        _target(valid_from=_SEP, until=_OCT, tx_start=_T1, value="1.00"),
    )
    bound = _bound(unit, [later.evidence.predecessor])  # type: ignore[union-attr]
    start, validation = (step for step in bound.steps if isinstance(step, PlannedClose))
    assert start.affected_rows.on_shortfall == FAILED_PRECONDITION
    assert (start.concurrency.observed_start, validation.concurrency.observed_start) == (  # type: ignore[union-attr]
        _T1,
        _T0,
    )
