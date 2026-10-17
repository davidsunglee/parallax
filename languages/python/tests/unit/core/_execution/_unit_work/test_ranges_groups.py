"""A Bitemporal amendment group settled at execution (`m-unit-work`
*Materialized Write Groups*, *Write Plan and Planned Writes*): each selected
object a range from the row it was selected by, settled in batches of complete
objects whose coverage is read in bounded statements, every milestone judged
for itself, and what success publishes accumulated as plain facts."""

from __future__ import annotations

import datetime as dt
from collections.abc import Iterable
from decimal import Decimal
from typing import Final

import pytest

from parallax.core import predicate as predicate_algebra
from parallax.core._execution._planning import build_write_planner
from parallax.core._execution._unit_work import ranges as ranges_module
from parallax.core._execution._unit_work.acquisition import CoverageReadRequest, CoverageTerm
from parallax.core._execution._unit_work.ranges import (
    DeferredGroupRange,
    GroupContinuation,
    coverage_requests,
)
from parallax.core.base import INFINITY
from parallax.core.metamodel import AttributeIdentity
from parallax.core.temporal_read import TimeInterval
from parallax.core.unit_work import (
    Concurrency,
    MaterializedWriteGroup,
    PredicateMutation,
    PredicateSelection,
    PredicateWrite,
    WriteAssignment,
    WritePlanningRequest,
)
from parallax.core.write_plan import (
    PlannedClose,
    PlannedInsert,
    PredecessorRow,
    PredecessorRows,
    WritePlanningError,
)
from parallax.core.write_plan.observe import AssignedComparison
from parallax.core.write_plan.plan import (
    NO_TEMPORAL_WRITE_OWNERSHIP,
    ExecutionUnit,
    OwnedEndpoint,
    PlannedWrites,
    TemporalWriteOwnership,
)
from parallax.core.write_plan.steps import INFINITY as OPEN_END
from parallax.core.write_plan.steps import (
    ChangedFrom,
    Finite,
    PlannedTemporalGuard,
    PlannedWrite,
)
from tests._support.clock_probes import instant_at
from tests._support.planner_probes import TEST_ACTOR_IDENTITY
from tests.unit._corpus_identity_support import corpus_entity, corpus_object_key
from tests.unit._corpus_model_support import model as corpus_model
from tests.unit._gc_reachability import reachable_objects
from tests.unit._temporal_group_support import temporal_group
from tests.unit.core._execution._unit_work._acquired_rows_support import HeldRows, prepared_group
from tests.unit.core._execution._unit_work._ownership_support import OpenedRows

_POSITION: Final = corpus_model("position")
_INSTANT: Final = instant_at("2024-06-01T00:00:00+00:00")
_JAN, _FEB, _MAR, _APR, _MAY, _JUN, _JUL, _SEP = (
    dt.datetime(2024, month, 1, tzinfo=dt.UTC) for month in (1, 2, 3, 4, 5, 6, 7, 9)
)


def _row(
    key: int, start: dt.datetime, end: object = INFINITY, *, value: str = "100.00"
) -> dict[str, object]:
    return {
        "id": key,
        "acctNum": "A",
        "value": Decimal(value),
        "validStart": start,
        "validEnd": end,
        "txStart": _JAN,
        "txEnd": INFINITY,
    }


def _group(
    *rows: dict[str, object], mutation: PredicateMutation = "amendUntil", value: str = "150.00"
) -> MaterializedWriteGroup:
    bounds = (_FEB, _JUN) if mutation.endswith("Until") else (_FEB,)
    return temporal_group(
        PredicateWrite(
            mutation,
            PredicateSelection(
                "Position",
                predicate_algebra.Comparison(
                    "eq", predicate_algebra.FieldSubject("Position.value"), "100.00"
                ),
            ),
            (WriteAssignment("Position.value", Decimal(value)),),
            *bounds,
        ),
        _POSITION,
        rows,
    )


def _unit(
    group: MaterializedWriteGroup,
    *,
    concurrency: Concurrency = "locking",
    counts_unchanged_rows: bool = False,
) -> ExecutionUnit:
    plan = build_write_planner(_POSITION).finalize(
        WritePlanningRequest(
            actor_identity=TEST_ACTOR_IDENTITY,
            transaction_instant=_INSTANT,
            concurrency=concurrency,
            buffered_writes=[group],
            counts_unchanged_rows=counts_unchanged_rows,
        )
    )
    assert len(plan.steps) == 0
    (unit,) = plan.units
    assert isinstance(unit.deferred, DeferredGroupRange)
    return unit


def _later(*rows: dict[str, object]) -> list[PredecessorRow]:
    return [PredecessorRow(members=row) for row in rows]


def _continuation(
    unit: ExecutionUnit,
    held: HeldRows,
    *,
    ownership: TemporalWriteOwnership = NO_TEMPORAL_WRITE_OWNERSHIP,
) -> GroupContinuation:
    return prepared_group(_POSITION, unit, held, transaction_instant=_INSTANT, ownership=ownership)


def _reading(*rows: dict[str, object]) -> HeldRows:
    """A coverage read answering the rows of ``rows`` it overlaps."""
    return HeldRows(_POSITION, _later(*rows), overlapping=True)


def _one_round(continuation: GroupContinuation) -> PlannedWrites:
    """The one round ``continuation`` settles, no other remaining after it."""
    writes = continuation.pull()
    assert writes is not None
    assert continuation.pull() is None
    return writes


def _windows(steps: Iterable[PlannedWrite]) -> list[tuple[str, object, object, object]]:
    shaped: list[tuple[str, object, object, object]] = []
    for step in steps:
        if isinstance(step, PlannedInsert):
            (entry,) = step.entries
            cells = {identity.name: value for identity, value in entry.row.attributes.items()}
            shaped.append(
                (
                    type(entry.origin).__name__,
                    cells["validStart"],
                    cells["validEnd"],
                    cells["value"],
                )
            )
        else:
            shaped.append((type(step).__name__, None, None, None))
    return shaped


def test_an_assignment_no_opened_row_expresses_is_refused_while_planning() -> None:
    group = temporal_group(
        PredicateWrite(
            "amendUntil",
            PredicateSelection(
                "Position",
                predicate_algebra.Comparison(
                    "eq", predicate_algebra.FieldSubject("Position.value"), "100.00"
                ),
            ),
            (WriteAssignment("Position.acctNum", {"increment": 1}),),
            _FEB,
            _JUN,
        ),
        _POSITION,
        [_row(1, _JAN, _APR)],
    )
    with pytest.raises(WritePlanningError, match="not recognized for insert planning"):
        _unit(group)


def test_a_start_equal_object_is_kept_and_its_later_coverage_still_changes() -> None:
    # February already holds the assigned 150 and April holds 200: the
    # starting milestone is kept whole under the shared lock, and April's is
    # amended through June, whatever it held — membership was fixed at February.
    continuation = _continuation(
        _unit(_group(_row(1, _JAN, _APR, value="150.00"))),
        _reading(_row(1, _APR, _JUL, value="200.00")),
    )
    assert _windows(_one_round(continuation)) == [
        ("PlannedClose", None, None, None),
        ("ChangedFrom", _APR, _JUN, Decimal("150.00")),
        ("CarriedFrom", _JUN, _JUL, Decimal("200.00")),
    ]
    assert [state.object for state in continuation.finish().changed] == [
        corpus_object_key("Position", ("id", 1))
    ]


def test_an_unchanged_start_under_optimistic_concurrency_is_kept_by_its_guard() -> None:
    continuation = _continuation(
        _unit(
            _group(_row(1, _JAN, _APR, value="150.00")),
            concurrency="optimistic",
            counts_unchanged_rows=True,
        ),
        _reading(_row(1, _APR, _JUL, value="200.00")),
    )
    guard, close, *_openings = _one_round(continuation)
    assert isinstance(guard, PlannedTemporalGuard)
    assert isinstance(close, PlannedClose)
    assert [step.target.key_values for step in (guard, close)] == [(1,), (1,)]


def test_an_amendment_preserves_the_gaps_its_window_crosses() -> None:
    held = _reading(_row(1, _APR, _JUL))
    continuation = _continuation(_unit(_group(_row(1, _JAN, _MAR))), held)
    assert _windows(_one_round(continuation)) == [
        ("PlannedClose", None, None, None),
        ("PlannedClose", None, None, None),
        ("CarriedFrom", _JAN, _FEB, Decimal("100.00")),
        ("ChangedFrom", _FEB, _MAR, Decimal("150.00")),
        ("ChangedFrom", _APR, _JUN, Decimal("150.00")),
        ("CarriedFrom", _JUN, _JUL, Decimal("100.00")),
    ]
    # The hole [Mar, Jun) the starting row leaves is read once.
    (read,) = held.requests
    assert isinstance(read, CoverageReadRequest)
    assert read.terms == (CoverageTerm(1, (TimeInterval(_MAR, _JUN),)),)


def test_an_object_whose_starting_row_covers_its_window_reads_nothing() -> None:
    held = _reading()
    continuation = _continuation(_unit(_group(_row(1, _JAN), _row(2, _JAN))), held)
    assert len(_one_round(continuation)) == 2 * 4
    assert held.requests == []


def test_a_completed_read_that_finds_nothing_leaves_a_gap_read_once() -> None:
    held = _reading()
    continuation = _continuation(_unit(_group(_row(1, _JAN, _MAR))), held)
    assert _windows(_one_round(continuation))[-1] == ("ChangedFrom", _FEB, _MAR, Decimal("150.00"))
    assert len(held.requests) == 1


def test_objects_settle_in_complete_batches_in_the_order_they_were_selected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Two objects a batch: every object of a batch is read in one statement
    # before any of them settles, an object needing no read still counts, and
    # each object's history settles whole inside its batch, an object read
    # further opening its two equal changed parts as one row.
    monkeypatch.setattr(ranges_module, "_GROUP_OBJECTS", 2)
    starts = [_row(key, _JAN, _MAR if key % 2 else INFINITY) for key in range(1, 6)]
    later = [_row(key, _MAR, _JUL) for key in range(1, 6, 2)]
    held = _reading(*later)
    continuation = _continuation(_unit(_group(*starts)), held)
    rounds: list[PlannedWrites] = []
    reads: list[int] = []
    for _batch in range(3):
        writes = continuation.pull()
        assert writes is not None
        rounds.append(writes)
        reads.append(len(held.requests))
    assert continuation.pull() is None
    assert [len(writes) for writes in rounds] == [4 + 5, 5 + 4, 5]
    # Every batch read what it needed before it settled, one read a batch.
    assert reads == [1, 2, 3]
    assert [
        [term.key_value for term in read.terms]
        for read in held.requests
        if isinstance(read, CoverageReadRequest)
    ] == [[1], [3], [5]]
    keys = [
        step.target.key_values[0]
        for writes in rounds
        for step in writes
        if isinstance(step, PlannedClose)
    ]
    assert keys == [1, 1, 2, 3, 3, 4, 5, 5]


def test_several_objects_share_a_read_and_one_object_may_span_several(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(ranges_module, "_COVERAGE_TERMS", 2)
    starts = [_row(key, _JAN, _MAR) for key in (1, 2, 3)]
    held = _reading()
    _one_round(_continuation(_unit(_group(*starts)), held))
    assert [
        [term.key_value for term in read.terms]
        for read in held.requests
        if isinstance(read, CoverageReadRequest)
    ] == [[1, 2], [3]]
    entity = _POSITION.entity(corpus_entity("Position"))
    assert entity is not None
    key = AttributeIdentity(entity.identity, "id")
    windows = tuple(
        TimeInterval(start, end) for start, end in ((_JAN, _FEB), (_MAR, _APR), (_MAY, _JUN))
    )
    requests = list(
        coverage_requests(
            entity, key, (CoverageTerm(1, windows), CoverageTerm(2, windows[:1])), locking=True
        )
    )
    assert [request.terms for request in requests] == [
        (CoverageTerm(1, windows[:2]),),
        (CoverageTerm(1, windows[2:]), CoverageTerm(2, windows[:1])),
    ]


def test_every_object_shares_one_assignment_set_and_one_prepared_comparison(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    prepared: list[object] = []
    original = AssignedComparison.__init__

    def counting(self: AssignedComparison, *args: object) -> None:
        prepared.append(self)
        original(self, *args)  # type: ignore[arg-type]

    monkeypatch.setattr(AssignedComparison, "__init__", counting)
    writes = _one_round(
        _continuation(_unit(_group(*(_row(key, _JAN) for key in range(1, 5)))), _reading())
    )
    changed = [
        entry
        for step in writes
        if isinstance(step, PlannedInsert)
        for entry in step.entries
        if isinstance(entry.origin, ChangedFrom)
    ]
    assert len(changed) == 4
    assert len({id(entry.executed) for entry in changed}) == 1
    assert len(prepared) == 1


def test_an_empty_round_is_not_exhaustion() -> None:
    # Every object's milestone already holds the assigned value under the
    # shared lock: the round executes nothing, and the next answers none.
    continuation = _continuation(_unit(_group(_row(1, _JAN, value="150.00"))), _reading())
    assert len(_one_round(continuation)) == 0
    assert list(continuation.finish().changed) == []


def test_effects_are_final_only_once_no_round_remains() -> None:
    unit = _unit(_group(_row(1, _JAN)))
    continuation = _continuation(unit, HeldRows(_POSITION))
    with pytest.raises(ValueError, match="every batch ran"):
        continuation.finish()
    assert continuation.pull() is not None
    with pytest.raises(ValueError, match="every batch ran"):
        continuation.finish()
    assert continuation.pull() is None
    effects = continuation.finish()
    continuation.close()
    # Closing releases what preparation held, not the facts it handed over.
    assert [state.object for state in effects.changed] == [corpus_object_key("Position", ("id", 1))]
    assert len(list(effects.opened.fresh)) == 3


def test_the_selected_rows_settle_through_one_continuation_only() -> None:
    unit = _unit(_group(_row(1, _JAN)))
    _continuation(unit, HeldRows(_POSITION))
    with pytest.raises(ValueError, match="one continuation"):
        _continuation(unit, HeldRows(_POSITION))


def test_a_completed_batch_releases_its_selected_rows(monkeypatch: pytest.MonkeyPatch) -> None:
    # The plan's description hands its rows over, and the continuation lets
    # each go as its batch takes it: what a finished batch settled is reachable
    # from neither once the next is prepared.
    monkeypatch.setattr(ranges_module, "_GROUP_OBJECTS", 1)
    group = _group(_row(1, _JAN), _row(2, _JAN))
    evidence = group.evidence
    assert isinstance(evidence, PredecessorRows)
    first, second = evidence.rows
    unit = _unit(group)
    del group, evidence
    continuation = _continuation(unit, HeldRows(_POSITION))
    assert continuation.pull() is not None
    held = {id(value) for value in reachable_objects(continuation)} | {
        id(value) for value in reachable_objects(unit)
    }
    assert id(first) not in held
    assert id(second) in held
    assert continuation.pull() is not None
    assert id(second) not in {id(value) for value in reachable_objects(continuation)}
    assert continuation.pull() is None


def test_an_inserted_row_the_amendment_reaches_continues_its_insertion() -> None:
    # The selected row is one an admitted insertion of this attempt opened:
    # it is revised in place, and what it opens continues that insertion; no
    # row the amendment reaches is removed.
    owned = OwnedEndpoint(corpus_entity("Position"), (1,), (Finite(instant=_APR), OPEN_END))
    ownership = OpenedRows(frozenset({owned}), frozenset({owned}))
    row = {**_row(1, _JAN, _APR), "txStart": dt.datetime(2024, 6, 1, tzinfo=dt.UTC)}
    plan = build_write_planner(_POSITION).finalize(
        WritePlanningRequest(
            actor_identity=TEST_ACTOR_IDENTITY,
            transaction_instant=_INSTANT,
            concurrency="locking",
            buffered_writes=[_group(row)],
            ownership=ownership,
        )
    )
    (unit,) = plan.units
    continuation = _continuation(unit, _reading(), ownership=ownership)
    assert [type(step).__name__ for step in _one_round(continuation)] == [
        "PlannedTemporalRevision",
        "PlannedInsert",
    ]
    effects = continuation.finish()
    assert list(effects.opened.continued) == [
        OwnedEndpoint(corpus_entity("Position"), (1,), (Finite(instant=_FEB), OPEN_END))
    ]
    assert list(effects.opened.fresh) == []
    assert list(effects.removed) == []


def test_an_owned_row_whose_changed_part_merges_with_a_later_rows_is_removed() -> None:
    # The selected row is the attempt's own [January, April); the later stored
    # row [April, July) takes the same value through June, so both changed
    # parts are one row, opened whole, and the owned row is removed.
    owned = OwnedEndpoint(corpus_entity("Position"), (1,), (Finite(instant=_APR), OPEN_END))
    ownership = OpenedRows(frozenset({owned}))
    row = {**_row(1, _JAN, _APR), "txStart": dt.datetime(2024, 6, 1, tzinfo=dt.UTC)}
    plan = build_write_planner(_POSITION).finalize(
        WritePlanningRequest(
            actor_identity=TEST_ACTOR_IDENTITY,
            transaction_instant=_INSTANT,
            concurrency="locking",
            buffered_writes=[_group(row)],
            ownership=ownership,
        )
    )
    (unit,) = plan.units
    continuation = _continuation(
        unit, _reading(_row(1, _APR, _JUL, value="200.00")), ownership=ownership
    )
    assert _windows(_one_round(continuation)) == [
        ("PlannedTemporalRemoval", None, None, None),
        ("PlannedClose", None, None, None),
        ("CarriedFrom", _JAN, _FEB, Decimal("100.00")),
        ("ChangedFrom", _FEB, _JUN, Decimal("150.00")),
        ("CarriedFrom", _JUN, _JUL, Decimal("200.00")),
    ]
    assert list(continuation.finish().removed) == [owned]
