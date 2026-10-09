"""What a temporal object's composed writes bind to (`m-temporal-write`
*Caller-addressed writes span their requested extent*), driven through range
binding without a database: the caller's start, a replacement's extent,
destruction, disjoint operations under one transform, and what a range after an
ordering barrier binds to once earlier units of its flush have run."""

from __future__ import annotations

import datetime as dt
from collections.abc import Sequence
from decimal import Decimal
from typing import Literal

import pytest

from parallax.core.base import INFINITY, TemporalBound
from parallax.core.execution._planning import build_write_planner
from parallax.core.temporal_read import TimeInterval
from parallax.core.unit_work import (
    CardinalityCorruptionError,
    OptimisticLockConflictError,
    RetainedObservation,
    StaleWriteError,
    TransactionInstant,
    WritePlanningRequest,
    WritePreconditionError,
)
from parallax.core.unit_work.acquisition import CoverageReadRequest
from parallax.core.unit_work.materialized import (
    BufferItem,
    ComposedTemporalWrite,
    ObservedKeyedWrite,
    TargetKeyedWrite,
    chained,
)
from parallax.core.unit_work.write_planner import compose_writes
from parallax.core.write_plan import (
    PlannedClose,
    PlannedInsert,
    PredecessorRow,
)
from parallax.core.write_plan.plan import (
    NO_TEMPORAL_WRITE_OWNERSHIP,
    OPEN_BITEMPORAL_ENDS,
    BoundRange,
    Derivation,
    Descent,
    ExecutionUnit,
    OwnedEndpoint,
    TemporalWriteOwnership,
)
from parallax.core.write_plan.steps import (
    FAILED_PRECONDITION,
    NEW_LINEAGE,
    OPTIMISTIC_CONFLICT,
    UNGATED,
    Finite,
    PlannedTemporalGuard,
    PlannedTemporalRevision,
)
from parallax.core.write_plan.steps import INFINITY as OPEN_END
from tests._support.clock_probes import instant_at
from tests._support.planner_probes import TEST_ACTOR_IDENTITY
from tests.unit.core.unit_work._acquired_rows_support import bind_held, coverage_read
from tests.unit.core.unit_work._ownership_support import OpenedRows
from tests.unit.core.unit_work._temporal_targets_support import (
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
    OCT,
    POSITION,
    SEP,
    START,
    T0,
    T1,
    WHOLE,
    T,
    addressed_write,
    observed_write,
    rectangle,
    retained,
)


# --------------------------------------------------------------------------- #
# Binding: the caller's start, replacement extent, and destruction.            #
# --------------------------------------------------------------------------- #
def _deferred_unit(
    *writes: BufferItem, concurrency: str = "optimistic", guards: bool = False
) -> ExecutionUnit:
    plan = build_write_planner(POSITION).finalize(
        WritePlanningRequest(
            actor_identity=TEST_ACTOR_IDENTITY,
            transaction_instant=instant_at("2024-10-01T00:00:00+00:00"),
            concurrency=concurrency,  # type: ignore[arg-type]
            buffered_writes=compose_writes(POSITION, list(writes)),
            counts_unchanged_rows=guards,
        )
    )
    (unit,) = plan.units
    assert unit.deferred is not None
    return unit


def _bound(
    unit: ExecutionUnit,
    rows: Sequence[PredecessorRow],
    *,
    ownership: TemporalWriteOwnership = NO_TEMPORAL_WRITE_OWNERSHIP,
) -> BoundRange:
    """``unit``'s deferred range bound, as the unit of work binds it at
    execution, to a coverage read finding ``rows`` under ``ownership``."""
    return bind_held(POSITION, unit, rows, transaction_instant=_instant(), ownership=ownership)


def _coverage(unit: ExecutionUnit) -> CoverageReadRequest:
    """The coverage read ``unit``'s deferred range asks for."""
    return coverage_read(POSITION, unit, transaction_instant=_instant())


def _instant() -> TransactionInstant:
    return instant_at("2024-10-01T00:00:00+00:00")


def _windows(bound: BoundRange) -> list[tuple[object, object, object]]:
    windows: list[tuple[object, object, object]] = []
    for step in bound.steps:
        if isinstance(step, PlannedInsert):
            (entry,) = step.entries
            cells = {identity.name: value for identity, value in entry.row.attributes.items()}
            windows.append((cells["validStart"], cells["validEnd"], cells["value"]))
    return windows


def test_a_range_its_observations_leave_uncovered_reads_only_the_uncovered_suffix() -> None:
    observed = observed_write(
        "amendUntil",
        retained(rectangle(JAN, JUN, "100.00")),
        valid_from=MAR,
        until=SEP,
        acctNum="O",
    )
    unit = _deferred_unit(observed)
    assert unit.deferred is not None
    (window,) = _coverage(unit).terms[0].valid_time_windows
    assert window == TimeInterval(JUN, SEP)
    prepared = observed.instruction.valid_time_window
    assert prepared is not None
    assert window.end is prepared.end


def test_a_lone_target_range_reads_through_the_very_window_its_caller_prepared() -> None:
    target = addressed_write(value="150.00")
    unit = _deferred_unit(target)
    assert unit.deferred is not None
    (window,) = _coverage(unit).terms[0].valid_time_windows
    assert window is target.instruction.valid_time_window


def test_a_target_range_reads_its_window_and_gates_its_start_on_the_callers_revision() -> None:
    unit = _deferred_unit(addressed_write(value="150.00"))
    assert unit.deferred is not None
    acquisition = _coverage(unit)
    assert (acquisition.terms[0].valid_time_windows, acquisition.locking) == (
        (TimeInterval(MAR, SEP),),
        False,
    )
    bound = _bound(unit, [START.evidence.predecessor, LATER.evidence.predecessor])  # type: ignore[union-attr]
    first, second = (step for step in bound.steps if isinstance(step, PlannedClose))
    assert first.affected_rows.on_shortfall == FAILED_PRECONDITION
    assert second.affected_rows.on_shortfall != FAILED_PRECONDITION
    assert _windows(bound) == [
        (JAN, MAR, Decimal("100.00")),
        (MAR, JUN, Decimal("150.00")),
        (JUN, SEP, Decimal("150.00")),
        (SEP, INFINITY, Decimal("200.00")),
    ]


@pytest.mark.parametrize(
    "coverage",
    [
        pytest.param([], id="no-coverage"),
        pytest.param([rectangle(JUN, INFINITY, "200.00")], id="a-gap-at-the-start"),
        pytest.param([rectangle(JAN, JUN, "100.00", tx_start=T1)], id="another-revision"),
    ],
)
def test_a_target_whose_start_does_not_stand_at_its_callers_revision_binds_nothing(
    coverage: list[PredecessorRow],
) -> None:
    unit = _deferred_unit(addressed_write(replaces=True, acctNum="Z", value="1.00"))
    with pytest.raises(WritePreconditionError) as refused:
        _bound(unit, coverage)
    assert (dict(refused.value.key), refused.value.expected) == ({"id": 1}, T0)


def test_a_replacement_fills_the_gaps_of_its_extent_once_and_a_destruction_fills_none() -> None:
    coverage = [rectangle(JAN, MAR + dt.timedelta(days=30), "100.00")]
    coverage.append(rectangle(JUN, DEC, "200.00"))
    replaced = _bound(
        _deferred_unit(addressed_write(replaces=True, until=None, acctNum="Z", value="9.00")),
        coverage,
    )
    assert _windows(replaced) == [
        (JAN, MAR, Decimal("100.00")),
        (MAR, MAR + dt.timedelta(days=30), Decimal("9.00")),
        (JUN, DEC, Decimal("9.00")),
        (MAR + dt.timedelta(days=30), JUN, Decimal("9.00")),
        (DEC, INFINITY, Decimal("9.00")),
    ]
    # The destruction observed [January, June), so the flush reads only the
    # coverage from June on.
    destroyed = _bound(
        _deferred_unit(
            addressed_write(replaces=True, until=None, acctNum="Z", value="9.00"),
            observed_write("terminate", START, until=None),
        ),
        [rectangle(JUN, DEC, "200.00")],
    )
    assert _windows(destroyed) == [(JAN, MAR, Decimal("100.00"))]
    first = next(step for step in destroyed.steps if isinstance(step, PlannedClose))
    assert first.affected_rows.on_shortfall == FAILED_PRECONDITION


def test_a_patch_after_a_replacement_keeps_its_extent_and_overlays_its_gaps() -> None:
    coverage = [rectangle(JAN, JUN, "100.00")]
    bound = _bound(
        _deferred_unit(
            addressed_write(replaces=True, acctNum="Z", value="9.00"),
            observed_write("amendUntil", START, value="7.00"),
            addressed_write(acctNum="Y"),
        ),
        coverage,
    )
    assert _windows(bound) == [
        (JAN, MAR, Decimal("100.00")),
        (MAR, JUN, Decimal("7.00")),
        (JUN, SEP, Decimal("7.00")),
    ]
    opened = [
        {identity.name: value for identity, value in step.entries[0].row.attributes.items()}
        for step in bound.steps
        if isinstance(step, PlannedInsert)
    ]
    assert [cells["acctNum"] for cells in opened] == ["A", "Y", "Y"]


def test_a_locking_target_range_reads_its_coverage_under_the_shared_lock_ungated() -> None:
    unit = _deferred_unit(addressed_write(value="150.00"), concurrency="locking")
    assert unit.deferred is not None
    assert _coverage(unit).locking
    bound = _bound(unit, [START.evidence.predecessor])  # type: ignore[union-attr]
    close = next(step for step in bound.steps if isinstance(step, PlannedClose))
    assert close.concurrency == UNGATED


# --------------------------------------------------------------------------- #
# Unchanged milestones: a caller's condition is authority, not new history.    #
# --------------------------------------------------------------------------- #
_COVERAGE = [rectangle(JAN, JUN, "100.00"), rectangle(JUN, INFINITY, "200.00", tx_start=T1)]


def test_an_equal_start_is_kept_by_a_guard_on_its_callers_revision_beside_later_changes() -> None:
    unit = _deferred_unit(addressed_write(value="100.00"), guards=True)
    bound = _bound(unit, _COVERAGE)
    guard, close, *_opened = bound.steps
    assert isinstance(guard, PlannedTemporalGuard)
    assert guard.concurrency.observed_start == T0
    assert guard.affected_rows.on_shortfall == FAILED_PRECONDITION
    assert isinstance(close, PlannedClose)
    assert close.affected_rows.on_shortfall == OPTIMISTIC_CONFLICT
    assert _windows(bound) == [(JUN, SEP, Decimal("100.00")), (SEP, INFINITY, Decimal("200.00"))]
    # Only the later rectangle's state changes; the kept start still stands.
    (changed,) = bound.changed
    assert changed.milestone.tx_time == T1  # type: ignore[attr-defined]


@pytest.mark.parametrize(
    ("concurrency", "guards", "kinds"),
    [
        ("locking", False, []),
        ("optimistic", False, [PlannedClose, PlannedInsert, PlannedInsert]),
    ],
    ids=["locking", "no-matched-row-count"],
)
def test_an_equal_start_needs_no_statement_under_locking_and_is_chained_where_unprovable(
    concurrency: str, guards: bool, kinds: list[type[object]]
) -> None:
    unit = _deferred_unit(
        addressed_write(value="100.00", until=JUN), concurrency=concurrency, guards=guards
    )
    bound = _bound(unit, _COVERAGE[:1])
    assert [type(step) for step in bound.steps] == kinds
    if kinds:
        closing = bound.steps[0]
        assert isinstance(closing, PlannedClose)
        # The fallback close keeps the classification its guard would have.
        assert closing.affected_rows.on_shortfall == FAILED_PRECONDITION
    else:
        assert tuple(bound.changed) == ()


def test_an_equal_replacement_keeps_what_it_holds_and_still_opens_its_gaps() -> None:
    coverage = [rectangle(JAN, APR, "100.00"), rectangle(JUN, INFINITY, "100.00", tx_start=T1)]
    unit = _deferred_unit(addressed_write(replaces=True, acctNum="A", value="100.00"), guards=True)
    bound = _bound(unit, coverage)
    start, later, gap = bound.steps
    assert isinstance(start, PlannedTemporalGuard)
    assert start.affected_rows.on_shortfall == FAILED_PRECONDITION
    assert isinstance(later, PlannedTemporalGuard)
    assert later.affected_rows.on_shortfall == OPTIMISTIC_CONFLICT
    assert _windows(bound) == [(APR, JUN, Decimal("100.00"))]
    assert isinstance(gap, PlannedInsert)
    (opening,) = gap.entries
    assert opening.origin is NEW_LINEAGE
    assert (tuple(bound.changed), bound.removed) == ((), ())


def test_an_equal_target_of_a_row_the_attempt_opened_is_kept_without_a_statement() -> None:
    opened = rectangle(JAN, INFINITY, "100.00", tx_start=T)
    owned = OpenedRows(frozenset({OwnedEndpoint(ENTITY, (1,), OPEN_BITEMPORAL_ENDS)}))
    bound = _bound(
        _deferred_unit(addressed_write(value="100.00", tx_start=T), guards=True),
        [opened],
        ownership=owned,
    )
    assert (bound.steps, tuple(bound.changed), bound.removed) == ((), (), ())


# --------------------------------------------------------------------------- #
# Binding disjoint operations: one transform per original, a guard per start.  #
# --------------------------------------------------------------------------- #
def test_disjoint_targets_over_one_original_transform_it_once_under_one_guard() -> None:
    unit = _deferred_unit(
        addressed_write(valid_from=FEB, until=APR, value="150.00"),
        addressed_write(valid_from=JUN, until=AUG, value="175.00"),
    )
    assert unit.deferred is not None
    assert _coverage(unit).terms[0].valid_time_windows == (TimeInterval(FEB, AUG),)
    bound = _bound(unit, [WHOLE.evidence.predecessor])  # type: ignore[union-attr]
    (close,) = (step for step in bound.steps if isinstance(step, PlannedClose))
    assert close.affected_rows.on_shortfall == FAILED_PRECONDITION
    assert _windows(bound) == [
        (JAN, FEB, Decimal("100.00")),
        (FEB, APR, Decimal("150.00")),
        (APR, JUN, Decimal("100.00")),
        (JUN, AUG, Decimal("175.00")),
        (AUG, INFINITY, Decimal("100.00")),
    ]


def test_disjoint_targets_over_distinct_originals_guard_each_start_in_authored_order() -> None:
    unit = _deferred_unit(
        addressed_write(valid_from=SEP, until=OCT, tx_start=T1, value="175.00"),
        addressed_write(valid_from=FEB, until=APR, value="150.00"),
    )
    later = rectangle(JUN, INFINITY, "200.00", tx_start=T1)
    bound = _bound(unit, [START.evidence.predecessor, later])  # type: ignore[union-attr]
    closes = [step for step in bound.steps if isinstance(step, PlannedClose)]
    # The first-authored start's guard runs first, whatever its Valid Time.
    assert [close.concurrency.observed_start for close in closes] == [T1, T0]  # type: ignore[union-attr]
    assert [close.affected_rows.on_shortfall for close in closes] == [FAILED_PRECONDITION] * 2


def test_a_disjoint_operations_stale_start_fails_as_its_own_callers_precondition() -> None:
    unit = _deferred_unit(
        addressed_write(valid_from=FEB, until=APR, value="150.00"),
        addressed_write(valid_from=JUN, until=AUG, tx_start=T1, value="175.00"),
    )
    with pytest.raises(WritePreconditionError) as refused:
        _bound(unit, [WHOLE.evidence.predecessor])  # type: ignore[union-attr]
    assert refused.value.expected == T1


def test_two_current_rows_at_any_operations_start_are_corruption() -> None:
    unit = _deferred_unit(
        addressed_write(valid_from=FEB, until=APR, value="150.00"),
        addressed_write(valid_from=JUN, until=AUG, value="175.00"),
    )
    overlapping = [rectangle(JAN, JUN, "100.00"), rectangle(MAY, DEC, "1.00", tx_start=T1)]
    overlapping.append(rectangle(JUN, SEP, "2.00", tx_start=T1))
    with pytest.raises(CardinalityCorruptionError):
        _bound(unit, overlapping)


def test_a_replacement_fills_only_its_own_window_beside_a_disjoint_destruction() -> None:
    later = rectangle(APR, INFINITY, "200.00", tx_start=T1)
    unit = _deferred_unit(
        addressed_write(replaces=True, valid_from=FEB, until=JUN, acctNum="Z", value="9.00"),
        observed_write("terminateUntil", retained(later), valid_from=JUL, until=SEP),
    )
    gapped = [rectangle(JAN, MAR, "100.00"), later]
    bound = _bound(unit, gapped)
    assert sorted(_windows(bound), key=lambda window: window[0]) == [  # type: ignore[arg-type, return-value]
        (JAN, FEB, Decimal("100.00")),
        (FEB, MAR, Decimal("9.00")),
        (MAR, APR, Decimal("9.00")),
        (APR, JUN, Decimal("9.00")),
        (JUN, JUL, Decimal("200.00")),
        (SEP, INFINITY, Decimal("200.00")),
    ]


# --------------------------------------------------------------------------- #
# Continuation across a barrier: what an earlier unit of the flush proved.     #
# --------------------------------------------------------------------------- #
def _chained_unit(
    *writes: BufferItem,
    leads: bool = False,
    follows: bool = True,
    concurrency: str = "optimistic",
) -> ExecutionUnit:
    (composed,) = compose_writes(POSITION, list(writes))
    assert isinstance(composed, ComposedTemporalWrite | TargetKeyedWrite | ObservedKeyedWrite)
    plan = build_write_planner(POSITION).finalize(
        WritePlanningRequest(
            actor_identity=TEST_ACTOR_IDENTITY,
            transaction_instant=instant_at("2024-10-01T00:00:00+00:00"),
            concurrency=concurrency,  # type: ignore[arg-type]
            buffered_writes=(chained(composed, "id", leads=leads, follows=follows),),
        )
    )
    (unit,) = plan.units
    return unit


def _endpoint(end: object) -> OwnedEndpoint:
    ends = OPEN_BITEMPORAL_ENDS if end is INFINITY else (Finite(instant=end), OPEN_END)
    return OwnedEndpoint(ENTITY, (1,), ends)


# What an earlier unit's patch of [February, April) left of [January, infinity).
_LEFT = ((JAN, FEB), (FEB, APR), (APR, INFINITY))


def _lineage(
    left: tuple[tuple[dt.datetime, dt.datetime | Literal[TemporalBound.INFINITY]], ...],
) -> tuple[tuple[OwnedEndpoint, TimeInterval], ...]:
    return tuple((_endpoint(end), TimeInterval(start, end)) for start, end in left)


def _proven(original: RetainedObservation = WHOLE) -> OpenedRows:
    rows = _lineage(_LEFT)
    return OpenedRows(
        endpoints=frozenset(endpoint for endpoint, _coverage in rows),
        proofs={original.key: Derivation(original.key, TimeInterval(JAN, INFINITY), None, rows)},
        descents={endpoint: Descent(coverage, original.key) for endpoint, coverage in rows},
    )


def _opened(start: dt.datetime, value: str = "100.00", **cells: object) -> PredecessorRow:
    row = rectangle(start, INFINITY, value, tx_start=T)
    return PredecessorRow(members={**row.members, **cells}) if cells else row


def test_a_following_range_reads_its_whole_window_and_discharges_a_proven_start() -> None:
    unit = _chained_unit(addressed_write(valid_from=JUN, until=AUG, value="175.00"))
    assert unit.deferred is not None
    assert _coverage(unit).terms[0].valid_time_windows == (TimeInterval(JUN, AUG),)
    bound = _bound(unit, [_opened(APR)], ownership=_proven())
    # The start now stands at the row the earlier unit derived from the
    # original the caller stated; that row is the attempt's own, so it is
    # revised in place rather than closed, and nothing gates on the caller.
    assert not any(isinstance(step, PlannedClose) for step in bound.steps)
    (revision,) = (step for step in bound.steps if isinstance(step, PlannedTemporalRevision))
    assert revision.affected_rows.on_shortfall != FAILED_PRECONDITION
    assert _windows(bound) == [
        (APR, JUN, Decimal("100.00")),
        (JUN, AUG, Decimal("175.00")),
    ]


@pytest.mark.parametrize(
    ("ownership", "coverage"),
    [
        pytest.param(OpenedRows(frozenset({_endpoint(INFINITY)})), [_opened(APR)], id="no-proof"),
        pytest.param(_proven(), [_opened(APR, txStart=T + dt.timedelta(days=1))], id="restamped"),
        pytest.param(_proven(), [_opened(MAY)], id="moved-start"),
        pytest.param(_proven(), [], id="removed"),
    ],
)
def test_a_following_start_no_intact_proof_carries_is_the_callers_precondition(
    ownership: OpenedRows, coverage: list[PredecessorRow]
) -> None:
    unit = _chained_unit(addressed_write(valid_from=JUN, until=AUG, value="175.00"))
    with pytest.raises(WritePreconditionError) as refused:
        _bound(unit, coverage, ownership=ownership)
    assert refused.value.expected == T0


def test_a_following_observed_write_binds_to_the_values_the_earlier_unit_left() -> None:
    unit = _chained_unit(
        observed_write("amendUntil", WHOLE, valid_from=JUN, until=AUG, acctNum="O"),
    )
    bound = _bound(unit, [_opened(APR, "150.00")], ownership=_proven())
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
        observed_write("amendUntil", WHOLE, valid_from=JUN, until=AUG, acctNum="O"),
        concurrency=concurrency,
    )
    with pytest.raises(error):
        _bound(
            unit,
            [rectangle(APR, INFINITY, "100.00", tx_start=T1)],
            ownership=OpenedRows(frozenset()),
        )


def test_a_following_observed_original_still_standing_binds_as_any_original() -> None:
    unit = _chained_unit(
        observed_write("amendUntil", WHOLE, valid_from=JUN, until=AUG, acctNum="O"),
    )
    bound = _bound(unit, [WHOLE.evidence.predecessor], ownership=OpenedRows(frozenset()))  # type: ignore[union-attr]
    (close,) = (step for step in bound.steps if isinstance(step, PlannedClose))
    assert close.concurrency.observed_start == T0  # type: ignore[union-attr]


def test_a_following_callers_precondition_outranks_a_lost_observation() -> None:
    unit = _chained_unit(
        observed_write("amendUntil", WHOLE, valid_from=FEB, until=APR, acctNum="O"),
        addressed_write(valid_from=JUN, until=AUG, value="175.00"),
    )
    with pytest.raises(WritePreconditionError):
        _bound(
            unit,
            [rectangle(JAN, INFINITY, "100.00", tx_start=T1)],
            ownership=OpenedRows(frozenset()),
        )


def test_a_leading_range_records_what_it_derived_from_each_original() -> None:
    unit = _chained_unit(
        addressed_write(valid_from=FEB, until=APR, value="150.00"), leads=True, follows=False
    )
    bound = _bound(unit, [WHOLE.evidence.predecessor])  # type: ignore[union-attr]
    (derivation,) = bound.derived
    assert derivation.original == WHOLE.key
    assert derivation.owned is None
    assert derivation.rows == _lineage(_LEFT)
    assert derivation.valid_time_coverage == TimeInterval(JAN, INFINITY)
    plain = _deferred_unit(addressed_write(valid_from=FEB, until=APR, value="150.00"))
    assert _bound(plain, [WHOLE.evidence.predecessor]).derived == ()  # type: ignore[union-attr]


def test_a_following_start_untouched_at_its_stated_start_is_judged_as_usual() -> None:
    later = rectangle(JUN, INFINITY, "200.00", tx_start=T1)
    unit = _chained_unit(
        addressed_write(valid_from=JUL, until=AUG, tx_start=T1, value="175.00"),
    )
    bound = _bound(unit, [later], ownership=OpenedRows(frozenset()))
    (close,) = (step for step in bound.steps if isinstance(step, PlannedClose))
    assert close.affected_rows.on_shortfall == FAILED_PRECONDITION


def _unproven_descent() -> OpenedRows:
    proven = _proven()
    return OpenedRows(endpoints=proven.endpoints, descents=proven.descents)


def _short_proof() -> OpenedRows:
    rows = _lineage(_LEFT)
    return OpenedRows(
        endpoints=frozenset(endpoint for endpoint, _coverage in rows),
        proofs={WHOLE.key: Derivation(WHOLE.key, TimeInterval(JAN, MAY), None, rows)},
        descents={endpoint: Descent(coverage, WHOLE.key) for endpoint, coverage in rows},
    )


@pytest.mark.parametrize(
    ("ownership", "tx_start"),
    [
        pytest.param(_unproven_descent(), T0, id="a-descent-nothing-proved"),
        pytest.param(_proven(), T1, id="another-revision-than-the-original"),
        pytest.param(_short_proof(), T0, id="a-start-outside-the-original"),
    ],
)
def test_a_following_start_whose_proof_names_another_state_is_the_callers_precondition(
    ownership: OpenedRows, tx_start: dt.datetime
) -> None:
    unit = _chained_unit(
        addressed_write(valid_from=JUN, until=AUG, tx_start=tx_start, value="175.00"),
    )
    with pytest.raises(WritePreconditionError):
        _bound(unit, [_opened(APR)], ownership=ownership)


def test_a_following_range_fails_where_another_row_derived_from_its_original_is_gone() -> None:
    left = ((JAN, FEB), (FEB, APR), (APR, JUL), (JUL, INFINITY))
    rows = _lineage(left)
    ownership = OpenedRows(
        endpoints=frozenset(endpoint for endpoint, _coverage in rows),
        proofs={WHOLE.key: Derivation(WHOLE.key, TimeInterval(JAN, INFINITY), None, rows)},
        descents={endpoint: Descent(coverage, WHOLE.key) for endpoint, coverage in rows},
    )
    unit = _chained_unit(addressed_write(valid_from=JUN, until=AUG, value="175.00"))
    # The start stands, but [July, infinity), derived from the same original
    # inside the window, does not.
    with pytest.raises(WritePreconditionError):
        _bound(
            unit,
            [PredecessorRow(members={**_opened(APR).members, "validEnd": JUL})],
            ownership=ownership,
        )


def test_a_leading_range_records_an_overlapped_observation_it_only_validated() -> None:
    earlier = retained(rectangle(JAN, JUN, "100.00"))
    later = retained(rectangle(MAR, INFINITY, "300.00", tx_start=T1))
    unit = _chained_unit(
        observed_write("amendUntil", earlier, valid_from=FEB, until=APR, acctNum="E"),
        observed_write("amendUntil", later, valid_from=MAY, until=JUL, acctNum="L"),
        leads=True,
        follows=False,
    )
    validated, transformed = _bound(unit, [later.evidence.predecessor]).derived  # type: ignore[union-attr]
    assert (validated.original, validated.rows) == (earlier.key, ())
    assert transformed.original == later.key


def test_a_callers_start_is_guarded_ahead_of_an_overlapped_observation_it_validates() -> None:
    earlier = retained(rectangle(JAN, JUN, "100.00"))
    later = retained(rectangle(MAR, INFINITY, "300.00", tx_start=T1))
    unit = _deferred_unit(
        observed_write("amendUntil", earlier, valid_from=FEB, until=MAR, acctNum="E"),
        observed_write("amendUntil", later, valid_from=MAY, until=JUL, acctNum="L"),
        addressed_write(valid_from=SEP, until=OCT, tx_start=T1, value="1.00"),
    )
    bound = _bound(unit, [later.evidence.predecessor])  # type: ignore[union-attr]
    start, validation = (step for step in bound.steps if isinstance(step, PlannedClose))
    assert start.affected_rows.on_shortfall == FAILED_PRECONDITION
    assert (start.concurrency.observed_start, validation.concurrency.observed_start) == (  # type: ignore[union-attr]
        T1,
        T0,
    )
