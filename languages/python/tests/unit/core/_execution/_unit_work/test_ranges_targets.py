"""What a temporal object's composed writes bind to (`m-temporal-write`
*Target writes span their requested extent*), driven through range
binding without a database: the coverage a range reads, a caller's unchanged
start, disjoint operations, and what a range binds to once earlier writes of
its object completed."""

from __future__ import annotations

import datetime as dt
from collections.abc import Sequence
from decimal import Decimal

import pytest

from parallax.core._execution._planning import build_write_planner
from parallax.core._execution._unit_work.acquisition import CoverageReadRequest
from parallax.core._execution._unit_work.write_items import (
    AdmittedWrite,
)
from parallax.core.base import INFINITY
from parallax.core.temporal_read import TimeInterval
from parallax.core.unit_work import (
    CardinalityCorruptionError,
    TransactionInstant,
    WritePlanningRequest,
    WritePreconditionError,
)
from parallax.core.write_plan import (
    PlannedClose,
    PlannedInsert,
    PredecessorRow,
    WritePlan,
)
from parallax.core.write_plan.plan import (
    NO_TEMPORAL_WRITE_OWNERSHIP,
    OPEN_BITEMPORAL_ENDS,
    BoundRange,
    SettledWrite,
    TemporalRowCoordinates,
    TemporalWriteOwnership,
)
from parallax.core.write_plan.steps import (
    FAILED_PRECONDITION,
    NEW_LINEAGE,
    OPTIMISTIC_CONFLICT,
    Finite,
    PlannedTemporalGuard,
)
from parallax.core.write_plan.steps import INFINITY as OPEN_END
from tests._support.clock_probes import instant_at
from tests._support.planner_probes import (
    TEST_ACTOR_IDENTITY,
    admitted_writes,
    settled_writes,
)
from tests.unit.core._execution._unit_work._acquired_rows_support import (
    alone,
    bind_held,
    coverage_read,
)
from tests.unit.core._execution._unit_work._ownership_support import OpenedRows
from tests.unit.core._execution._unit_work._temporal_targets_support import (
    APR,
    AUG,
    DEC,
    ENTITY,
    FEB,
    JAN,
    JUL,
    JUN,
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
# Binding: the coverage a range reads.                                         #
# --------------------------------------------------------------------------- #
def _deferred_write(
    *writes: AdmittedWrite, concurrency: str = "optimistic", guards: bool = False
) -> SettledWrite:
    write = _planned_write(*writes, concurrency=concurrency, guards=guards)
    assert write.deferred is not None
    return write


def _planned_write(
    *writes: AdmittedWrite,
    concurrency: str = "optimistic",
    guards: bool = False,
    ownership: TemporalWriteOwnership = NO_TEMPORAL_WRITE_OWNERSHIP,
) -> SettledWrite:
    (write,) = settled_writes(
        _plan(*writes, concurrency=concurrency, guards=guards, ownership=ownership)
    )
    return write


def _plan(
    *writes: AdmittedWrite,
    concurrency: str = "optimistic",
    guards: bool = False,
    ownership: TemporalWriteOwnership = NO_TEMPORAL_WRITE_OWNERSHIP,
) -> WritePlan:
    return build_write_planner(POSITION).finalize(
        WritePlanningRequest(
            actor_identity=TEST_ACTOR_IDENTITY,
            transaction_instant=instant_at("2024-10-01T00:00:00+00:00"),
            preference=concurrency,  # type: ignore[arg-type]
            composed_writes=admitted_writes(POSITION, list(writes)),
            ownership=ownership,
            counts_unchanged_rows=guards,
        )
    )


def _bound(
    settled: SettledWrite,
    rows: Sequence[PredecessorRow],
    *,
    ownership: TemporalWriteOwnership = NO_TEMPORAL_WRITE_OWNERSHIP,
) -> BoundRange:
    """``settled write``'s deferred range bound, as the unit of work binds it at
    execution, to a coverage read finding ``rows`` under ``ownership``."""
    return bind_held(
        POSITION, alone(settled), rows, transaction_instant=_instant(), ownership=ownership
    )


def _coverage(settled: SettledWrite) -> CoverageReadRequest:
    """The coverage read ``settled write``'s deferred range asks for."""
    return coverage_read(POSITION, alone(settled), transaction_instant=_instant())


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
    settled = _deferred_write(observed)
    assert settled.deferred is not None
    (window,) = _coverage(settled).terms[0].valid_time_windows
    assert window == TimeInterval(JUN, SEP)
    prepared = observed.instruction.valid_time_window
    assert prepared is not None
    assert window.end is prepared.end


def test_a_lone_target_range_reads_through_the_very_window_its_caller_prepared() -> None:
    target = addressed_write(value="150.00")
    settled = _deferred_write(target)
    assert settled.deferred is not None
    (window,) = _coverage(settled).terms[0].valid_time_windows
    assert window is target.instruction.valid_time_window


# --------------------------------------------------------------------------- #
# Unchanged milestones: a caller's condition is authority, not new history.    #
# --------------------------------------------------------------------------- #
_COVERAGE = [rectangle(JAN, JUN, "100.00"), rectangle(JUN, INFINITY, "200.00", tx_start=T1)]


def test_an_equal_start_is_kept_by_a_guard_on_its_callers_revision_beside_later_changes() -> None:
    settled = _deferred_write(addressed_write(value="100.00"), guards=True)
    bound = _bound(settled, _COVERAGE)
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
        ("optimistic", False, [PlannedClose, PlannedInsert]),
    ],
    ids=["locking", "no-matched-row-count"],
)
def test_an_equal_start_needs_no_statement_under_locking_and_is_chained_where_unprovable(
    concurrency: str, guards: bool, kinds: list[type[object]]
) -> None:
    settled = _deferred_write(
        addressed_write(value="100.00", until=JUN), concurrency=concurrency, guards=guards
    )
    bound = _bound(settled, _COVERAGE[:1])
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
    settled = _deferred_write(
        addressed_write(replaces=True, acctNum="A", value="100.00"), guards=True
    )
    bound = _bound(settled, coverage)
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


# --------------------------------------------------------------------------- #
# Binding disjoint operations: a guard per start.                              #
# --------------------------------------------------------------------------- #


def test_disjoint_targets_over_distinct_originals_guard_each_start_in_authored_order() -> None:
    settled = _deferred_write(
        addressed_write(valid_from=SEP, until=OCT, tx_start=T1, value="175.00"),
        addressed_write(valid_from=FEB, until=APR, value="150.00"),
    )
    later = rectangle(JUN, INFINITY, "200.00", tx_start=T1)
    bound = _bound(settled, [START.evidence.predecessor, later])  # type: ignore[union-attr]
    closes = [step for step in bound.steps if isinstance(step, PlannedClose)]
    # The first-authored start's guard runs first, whatever its Valid Time.
    assert [close.concurrency.observed_start for close in closes] == [T1, T0]  # type: ignore[union-attr]
    assert [close.affected_rows.on_shortfall for close in closes] == [FAILED_PRECONDITION] * 2


def test_a_disjoint_operations_stale_start_fails_as_its_own_callers_precondition() -> None:
    settled = _deferred_write(
        addressed_write(valid_from=FEB, until=APR, value="150.00"),
        addressed_write(valid_from=JUN, until=AUG, tx_start=T1, value="175.00"),
    )
    with pytest.raises(WritePreconditionError) as refused:
        _bound(settled, [WHOLE.evidence.predecessor])  # type: ignore[union-attr]
    assert refused.value.expected == T1


def test_two_current_rows_at_any_operations_start_are_corruption() -> None:
    settled = _deferred_write(
        addressed_write(valid_from=FEB, until=APR, value="150.00"),
        addressed_write(valid_from=JUN, until=AUG, value="175.00"),
    )
    overlapping = [rectangle(JAN, JUN, "100.00"), rectangle(MAY, DEC, "1.00", tx_start=T1)]
    overlapping.append(rectangle(JUN, SEP, "2.00", tx_start=T1))
    with pytest.raises(CardinalityCorruptionError):
        _bound(settled, overlapping)


# --------------------------------------------------------------------------- #
# A range planned once earlier writes of its object completed.                  #
# --------------------------------------------------------------------------- #
def _coordinates(end: object) -> TemporalRowCoordinates:
    ends = OPEN_BITEMPORAL_ENDS if end is INFINITY else (Finite(instant=end), OPEN_END)
    return TemporalRowCoordinates(ENTITY, (1,), ends)


# What an earlier settled write's patch of [February, April) left of [January, infinity).
_LEFT = ((JAN, FEB), (FEB, APR), (APR, INFINITY))


def _changed() -> OpenedRows:
    """An attempt whose earlier write left ``_LEFT`` of ``WHOLE``, owning every
    row it opened."""
    return OpenedRows(
        frozenset(_coordinates(end) for _start, end in _LEFT),
        continuing={WHOLE: tuple(TimeInterval(start, end) for start, end in _LEFT)},
    )


def _opened(start: dt.datetime, value: str) -> PredecessorRow:
    return rectangle(start, INFINITY, value, tx_start=T)


def test_a_continuing_observed_write_binds_to_the_values_the_earlier_write_left() -> None:
    # The attempt holds none of the rows the earlier write left, so the range
    # reads them as ordinary coverage.
    settled = _planned_write(
        observed_write("amendUntil", WHOLE, valid_from=JUN, until=AUG, acctNum="O"),
        ownership=_changed(),
    )
    assert settled.deferred is not None
    bound = _bound(settled, [_opened(APR, "150.00")], ownership=_changed())
    opened = [
        {identity.name: value for identity, value in step.entries[0].row.attributes.items()}
        for step in bound.steps
        if isinstance(step, PlannedInsert)
    ]
    # The unassigned value is the current row's, never the observed state's.
    assert [(cells["acctNum"], cells["value"]) for cells in opened] == [
        ("A", Decimal("150.00")),
        ("O", Decimal("150.00")),
    ]


# --------------------------------------------------------------------------- #
# A caller's start beside an observation its range only validates.            #
# --------------------------------------------------------------------------- #


def test_a_callers_start_is_guarded_ahead_of_an_overlapped_observation_it_validates() -> None:
    earlier = retained(rectangle(JAN, JUN, "100.00"))
    later = retained(rectangle(MAR, INFINITY, "300.00", tx_start=T1))
    settled = _deferred_write(
        observed_write("amendUntil", earlier, valid_from=FEB, until=MAR, acctNum="E"),
        observed_write("amendUntil", later, valid_from=MAY, until=JUL, acctNum="L"),
        addressed_write(valid_from=SEP, until=OCT, tx_start=T1, value="1.00"),
    )
    bound = _bound(settled, [later.evidence.predecessor])  # type: ignore[union-attr]
    start, validation = (step for step in bound.steps if isinstance(step, PlannedClose))
    assert start.affected_rows.on_shortfall == FAILED_PRECONDITION
    assert (start.concurrency.observed_start, validation.concurrency.observed_start) == (  # type: ignore[union-attr]
        T1,
        T0,
    )
