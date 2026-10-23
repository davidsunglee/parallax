"""What a temporal object's composed writes bind to (`m-temporal-write`
*Target writes span their requested extent*), driven through range
binding without a database: the caller's start, a replacement's extent,
destruction, disjoint operations under one transform, what a range binds to
once earlier writes of its object completed, and what a range leaves for the
sources the attempt may still continue."""

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
    RetainedObservation,
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
    DerivedRow,
    SettledWrite,
    TemporalRowCoordinates,
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
from tests._support.planner_probes import (
    TEST_ACTOR_IDENTITY,
    admitted_writes,
    plan_steps,
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
    LATER,
    MAR,
    MAY,
    OBJECT,
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
            concurrency=concurrency,  # type: ignore[arg-type]
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


def test_a_target_range_reads_its_window_and_gates_its_start_on_the_callers_revision() -> None:
    settled = _deferred_write(addressed_write(value="150.00"))
    assert settled.deferred is not None
    acquisition = _coverage(settled)
    assert (acquisition.terms[0].valid_time_windows, acquisition.locking) == (
        (TimeInterval(MAR, SEP),),
        False,
    )
    bound = _bound(settled, [START.evidence.predecessor, LATER.evidence.predecessor])  # type: ignore[union-attr]
    first, second = (step for step in bound.steps if isinstance(step, PlannedClose))
    assert first.affected_rows.on_shortfall == FAILED_PRECONDITION
    assert second.affected_rows.on_shortfall != FAILED_PRECONDITION
    # Each rectangle's changed part holds the same complete state: one row.
    assert _windows(bound) == [
        (JAN, MAR, Decimal("100.00")),
        (MAR, SEP, Decimal("150.00")),
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
    settled = _deferred_write(addressed_write(replaces=True, acctNum="Z", value="1.00"))
    with pytest.raises(WritePreconditionError) as refused:
        _bound(settled, coverage)
    assert (dict(refused.value.key), refused.value.expected) == ({"id": 1}, T0)


def test_a_replacement_fills_the_gaps_of_its_extent_once_and_a_destruction_fills_none() -> None:
    coverage = [rectangle(JAN, MAR + dt.timedelta(days=30), "100.00")]
    coverage.append(rectangle(JUN, DEC, "200.00"))
    replaced = _bound(
        _deferred_write(addressed_write(replaces=True, until=None, acctNum="Z", value="9.00")),
        coverage,
    )
    # Every replaced part and every gap holds the one complete state, so the
    # whole extent opens as one row.
    assert _windows(replaced) == [
        (JAN, MAR, Decimal("100.00")),
        (MAR, INFINITY, Decimal("9.00")),
    ]
    # The destruction observed [January, June), so the flush reads only the
    # coverage from June on.
    destroyed = _bound(
        _deferred_write(
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
        _deferred_write(
            addressed_write(replaces=True, acctNum="Z", value="9.00"),
            observed_write("amendUntil", START, value="7.00"),
            addressed_write(acctNum="Y"),
        ),
        coverage,
    )
    assert _windows(bound) == [
        (JAN, MAR, Decimal("100.00")),
        (MAR, SEP, Decimal("7.00")),
    ]
    opened = [
        {identity.name: value for identity, value in step.entries[0].row.attributes.items()}
        for step in bound.steps
        if isinstance(step, PlannedInsert)
    ]
    assert [cells["acctNum"] for cells in opened] == ["A", "Y"]


def test_a_locking_target_range_reads_its_coverage_under_the_shared_lock_ungated() -> None:
    settled = _deferred_write(addressed_write(value="150.00"), concurrency="locking")
    assert settled.deferred is not None
    assert _coverage(settled).locking
    bound = _bound(settled, [START.evidence.predecessor])  # type: ignore[union-attr]
    close = next(step for step in bound.steps if isinstance(step, PlannedClose))
    assert close.concurrency == UNGATED


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


def test_an_equal_target_of_a_row_the_attempt_opened_is_kept_without_a_statement() -> None:
    opened = rectangle(JAN, INFINITY, "100.00", tx_start=T)
    owned = OpenedRows(frozenset({TemporalRowCoordinates(ENTITY, (1,), OPEN_BITEMPORAL_ENDS)}))
    bound = _bound(
        _deferred_write(addressed_write(value="100.00", tx_start=T), guards=True),
        [opened],
        ownership=owned,
    )
    assert (tuple(bound.steps), tuple(bound.changed), bound.removed) == ((), (), ())


# --------------------------------------------------------------------------- #
# Binding disjoint operations: one transform per original, a guard per start.  #
# --------------------------------------------------------------------------- #
def test_disjoint_targets_over_one_original_transform_it_once_under_one_guard() -> None:
    settled = _deferred_write(
        addressed_write(valid_from=FEB, until=APR, value="150.00"),
        addressed_write(valid_from=JUN, until=AUG, value="175.00"),
    )
    assert settled.deferred is not None
    assert _coverage(settled).terms[0].valid_time_windows == (TimeInterval(FEB, AUG),)
    bound = _bound(settled, [WHOLE.evidence.predecessor])  # type: ignore[union-attr]
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


def test_a_replacement_fills_only_its_own_window_beside_a_disjoint_destruction() -> None:
    later = rectangle(APR, INFINITY, "200.00", tx_start=T1)
    settled = _deferred_write(
        addressed_write(replaces=True, valid_from=FEB, until=JUN, acctNum="Z", value="9.00"),
        observed_write("terminateUntil", retained(later), valid_from=JUL, until=SEP),
    )
    gapped = [rectangle(JAN, MAR, "100.00"), later]
    bound = _bound(settled, gapped)
    assert sorted(_windows(bound), key=lambda window: window[0]) == [  # type: ignore[arg-type, return-value]
        (JAN, FEB, Decimal("100.00")),
        (FEB, JUN, Decimal("9.00")),
        (JUN, JUL, Decimal("200.00")),
        (SEP, INFINITY, Decimal("200.00")),
    ]


# --------------------------------------------------------------------------- #
# A range planned once earlier writes of its object completed.                  #
# --------------------------------------------------------------------------- #
def _coordinates(end: object) -> TemporalRowCoordinates:
    ends = OPEN_BITEMPORAL_ENDS if end is INFINITY else (Finite(instant=end), OPEN_END)
    return TemporalRowCoordinates(ENTITY, (1,), ends)


# What an earlier settled write's patch of [February, April) left of [January, infinity).
_LEFT = ((JAN, FEB), (FEB, APR), (APR, INFINITY))


def _changed(original: RetainedObservation = WHOLE) -> OpenedRows:
    """An attempt whose earlier write left ``_LEFT`` of ``original``, owning
    every row it opened."""
    return OpenedRows(
        frozenset(_coordinates(end) for _start, end in _LEFT),
        continuing={original: tuple(TimeInterval(start, end) for start, end in _LEFT)},
    )


def _opened(start: dt.datetime, value: str = "100.00", **cells: object) -> PredecessorRow:
    row = rectangle(start, INFINITY, value, tx_start=T)
    return PredecessorRow(members={**row.members, **cells}) if cells else row


@pytest.mark.parametrize(
    "coverage",
    [
        pytest.param([_opened(APR)], id="replaced"),
        pytest.param([_opened(APR, txStart=T + dt.timedelta(days=1))], id="restamped"),
        pytest.param([_opened(MAY)], id="moved-start"),
        pytest.param([], id="removed"),
    ],
)
def test_a_later_start_the_earlier_write_replaced_is_the_callers_precondition(
    coverage: list[PredecessorRow],
) -> None:
    settled = _deferred_write(addressed_write(valid_from=JUN, until=AUG, value="175.00"))
    assert _coverage(settled).terms[0].valid_time_windows == (TimeInterval(JUN, AUG),)
    # The caller's condition is literal: what the earlier write derived from
    # the state it names proves nothing for it.
    with pytest.raises(WritePreconditionError) as refused:
        _bound(settled, coverage, ownership=_changed())
    assert refused.value.expected == T0


def test_a_later_start_stated_at_the_row_the_earlier_write_left_revises_it() -> None:
    settled = _deferred_write(
        addressed_write(valid_from=JUN, until=AUG, tx_start=T, value="175.00")
    )
    bound = _bound(settled, [_opened(APR)], ownership=_changed())
    # That row is the attempt's own, so it is revised in place rather than
    # closed, and its start is the caller's to state.
    assert not any(isinstance(step, PlannedClose) for step in bound.steps)
    (revision,) = (step for step in bound.steps if isinstance(step, PlannedTemporalRevision))
    assert revision.affected_rows.on_shortfall == FAILED_PRECONDITION
    assert _windows(bound) == [
        (APR, JUN, Decimal("100.00")),
        (JUN, AUG, Decimal("175.00")),
    ]


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


def test_a_continuing_observed_write_binds_rows_the_attempt_holds_without_reading() -> None:
    held = _opened(APR, "150.00")
    ownership = OpenedRows(
        frozenset(_coordinates(end) for _start, end in _LEFT),
        continuing={WHOLE: tuple(TimeInterval(start, end) for start, end in _LEFT)},
        current={OBJECT: (held,)},
    )
    plan = _plan(
        observed_write("amendUntil", WHOLE, valid_from=JUN, until=AUG, acctNum="O"),
        ownership=ownership,
    )
    (write,) = settled_writes(plan)
    assert write.deferred is None
    opened = [
        {identity.name: value for identity, value in step.entries[0].row.attributes.items()}
        for step in plan_steps(plan)
        if isinstance(step, PlannedInsert)
    ]
    assert [(cells["validEnd"], cells["value"]) for cells in opened] == [
        (JUN, Decimal("150.00")),
        (AUG, Decimal("150.00")),
    ]


def test_a_later_start_untouched_at_its_stated_start_is_judged_as_usual() -> None:
    later = rectangle(JUN, INFINITY, "200.00", tx_start=T1)
    settled = _deferred_write(
        addressed_write(valid_from=JUL, until=AUG, tx_start=T1, value="175.00"),
    )
    bound = _bound(settled, [later], ownership=OpenedRows(frozenset()))
    (close,) = (step for step in bound.steps if isinstance(step, PlannedClose))
    assert close.affected_rows.on_shortfall == FAILED_PRECONDITION


# --------------------------------------------------------------------------- #
# What a range leaves of a predecessor a continuable source reaches.            #
# --------------------------------------------------------------------------- #
def test_a_range_records_what_it_left_of_each_demanded_predecessor() -> None:
    settled = _deferred_write(addressed_write(valid_from=FEB, until=APR, value="150.00"))
    bound = _bound(
        settled,
        [WHOLE.evidence.predecessor],  # type: ignore[union-attr]
        ownership=OpenedRows(frozenset(), demanded_states=frozenset({WHOLE.key})),
    )
    (derivation,) = bound.derived
    assert derivation.predecessor == WHOLE.key
    assert derivation.input_coordinates is None
    assert derivation.rows == tuple(
        DerivedRow(_coordinates(end), TimeInterval(start, end), TimeInterval(start, end))
        for start, end in _LEFT
    )
    assert derivation.valid_time_coverage == TimeInterval(JAN, INFINITY)
    assert [output.coordinates for output in bound.current_outputs] == [
        _coordinates(end) for _start, end in _LEFT
    ]
    assert _bound(settled, [WHOLE.evidence.predecessor]).derived == ()  # type: ignore[union-attr]


def test_a_range_records_an_overlapped_demanded_observation_it_only_validated() -> None:
    earlier = retained(rectangle(JAN, JUN, "100.00"))
    later = retained(rectangle(MAR, INFINITY, "300.00", tx_start=T1))
    settled = _deferred_write(
        observed_write("amendUntil", earlier, valid_from=FEB, until=APR, acctNum="E"),
        observed_write("amendUntil", later, valid_from=MAY, until=JUL, acctNum="L"),
    )
    validated, transformed = _bound(
        settled,
        [later.evidence.predecessor],  # type: ignore[union-attr]
        ownership=OpenedRows(frozenset(), demanded_states=frozenset({earlier.key, later.key})),
    ).derived
    assert (validated.predecessor, validated.rows) == (earlier.key, ())
    assert transformed.predecessor == later.key


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


# --------------------------------------------------------------------------- #
# A caller's start in a row merged from several predecessors.                    #
# --------------------------------------------------------------------------- #
_MERGED_ROW = rectangle(MAR, SEP, "150.00", tx_start=T)


@pytest.mark.parametrize(
    ("valid_from", "until", "tx_start"),
    [(APR, MAY, T0), (JUL, AUG, T1), (JUL, AUG, T0)],
    ids=["first-predecessors-start", "second-predecessors-start", "another-part"],
)
def test_a_start_in_a_merged_row_stated_at_a_predecessors_revision_is_refused(
    valid_from: dt.datetime, until: dt.datetime, tx_start: dt.datetime
) -> None:
    settled = _deferred_write(
        addressed_write(valid_from=valid_from, until=until, tx_start=tx_start, value="175.00")
    )
    with pytest.raises(WritePreconditionError):
        _bound(settled, [_MERGED_ROW], ownership=OpenedRows(frozenset({_coordinates(SEP)})))


def test_a_start_in_a_merged_row_stated_at_its_own_revision_revises_it_in_place() -> None:
    settled = _deferred_write(
        addressed_write(valid_from=APR, until=MAY, tx_start=T, value="175.00")
    )
    bound = _bound(settled, [_MERGED_ROW], ownership=OpenedRows(frozenset({_coordinates(SEP)})))
    assert not any(isinstance(step, PlannedClose) for step in bound.steps)
    assert any(isinstance(step, PlannedTemporalRevision) for step in bound.steps)
