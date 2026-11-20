"""How deferred writes form acquisition spans and how a span's Write Groups
are read and bound (`m-unit-work` *Shared coverage acquisition*), over ranges
real settlement deferred and the in-memory acquisition.

An unbroken run of deferred writes forms spans that each read alike, name each
object once, and hold at most the span bound. A span's uncovered parts are read
in shared reads packed in range order — a Bitemporal range's in Valid-Time
order, a Transaction-Time-Only range's one current row whole — each range ready
once the read naming its last part succeeded, and the leading ready ranges are
bound together as one Write Group only when the flush advances to it."""

from __future__ import annotations

import contextlib
import datetime as dt
from collections.abc import Callable, Sequence
from dataclasses import dataclass, replace
from types import FrameType
from typing import Any, cast

import pytest

from parallax.core import Attr, Bitemporal, DomainModel, InternalError, TxTemporal, attr
from parallax.core._execution._planning import build_write_planner
from parallax.core._execution._unit_work import acquisition_spans as spans_module
from parallax.core._execution._unit_work import write_plan as plan_module
from parallax.core._execution._unit_work import write_planner as planner_module
from parallax.core._execution._unit_work.acquisition_spans import (
    AcquisitionSpan,
    SpanWriteGroups,
    form_spans,
    write_groups,
)
from parallax.core._execution._unit_work.effects import (
    CARDINALITY_CORRUPTION,
    WRITE_PRECONDITION_FAILED,
    WritePreconditionError,
)
from parallax.core._execution._unit_work.evidence import ParticipationToken, ReadEvidence
from parallax.core._execution._unit_work.instructions import (
    PreparedTargetInstruction,
)
from parallax.core._execution._unit_work.preparation import WIRE
from parallax.core._execution._unit_work.ranges import DeferredRange
from parallax.core._execution._unit_work.row_acquisition import (
    AcquireRows,
    CompletionRequest,
    CoverageReadKey,
    CoverageReadRequest,
    RetainedStartingRow,
    RowConsumer,
    RowRequest,
)
from parallax.core._execution._unit_work.write_items import (
    AdmittedWrite,
    LicensedWrite,
    StateObserved,
    TxStartConditioned,
    is_licensed_by,
    target_write,
)
from parallax.core._execution._unit_work.write_plan import SettledWrite, WriteGroup, WritePlan
from parallax.core.internal.base import INFINITY
from parallax.core.internal.concurrency import ConcurrencyPreference
from parallax.core.internal.db_error import DatabaseError
from parallax.core.internal.entity._construction_input import ABSENT
from parallax.core.internal.entity._model import model_of
from parallax.core.internal.inheritance import inheritance_facet_of
from parallax.core.internal.metamodel import AttributeIdentity, Metamodel
from parallax.core.internal.planned_step import ObjectKey, PredecessorRow, PredecessorRows
from parallax.core.internal.planned_step.keys import ObjectStateKey, TemporalObjectStateKey
from parallax.core.internal.planned_step.steps import (
    MilestoneTarget,
    PlannedClose,
    PlannedInsert,
    PlannedStep,
)
from parallax.core.internal.planned_step.write_effects import (
    NO_TEMPORAL_WRITE_OWNERSHIP,
    BoundRange,
    WriteEffects,
)
from parallax.core.internal.temporal_read import milestone_edge, temporal_facet_of
from parallax.core.internal.unit_work import (
    KeyedWriteInstruction,
    TargetWriteInstruction,
    WritePlanningRequest,
    admitted_write,
)
from tests._support.bindings import bound_model
from tests._support.clock_probes import instant_at
from tests._support.errors import raises_code
from tests._support.planner_probes import TEST_ACTOR_IDENTITY, admitted_writes, deferred_ranges
from tests._support.write_preparation import prepare_instruction, write_preparation_of
from tests.unit._corpus_model_support import model as corpus_model
from tests.unit._positional_row_support import positional_row
from tests.unit.core._execution._reach_support import frames, reaches
from tests.unit.core._execution._unit_work._acquired_rows_support import HeldRows
from tests.unit.core._execution._unit_work._covered_target_support import covered_target
from tests.unit.core._shared_coverage_support import (
    AT,
    MODEL,
    T0,
    ShareCols,
    ShareDoc,
    day,
    frag,
    frag_rows,
    observation,
    plan,
    rectangle,
)

# --------------------------------------------------------------------------- #
# Formation: an unbroken run of deferred writes, as spans.                    #
# --------------------------------------------------------------------------- #
_BALANCE = corpus_model("balance")
_JAN = dt.datetime(2024, 1, 1, tzinfo=dt.UTC)


def _bitemporal(
    *keys: int,
    entity: type[ShareCols | ShareDoc] = ShareCols,
    concurrency: ConcurrencyPreference = "optimistic",
) -> tuple[DeferredRange, ...]:
    """The deferred range of one Bitemporal write of each object ``keys``
    names, settled in one finalization."""
    writes = [write for key in keys for write in frag(entity, key, 1)]
    return deferred_ranges(plan(writes, concurrency=concurrency))


def _transaction_time_only(*keys: int) -> tuple[DeferredRange, ...]:
    """The deferred range of one Optimistic Transaction-Time-Only target
    amendment of each object ``keys`` names, settled in one finalization."""
    targets = [
        target_write(
            prepare_instruction(
                TargetWriteInstruction(
                    "amend", "Balance", {"id": key, "value": "9.00"}, if_tx_start=_JAN
                ),
                write_preparation_of(_BALANCE),
                WIRE,
            ),
            inheritance_facet_of(_BALANCE),
        )
        for key in keys
    ]
    planned = build_write_planner(bound_model(_BALANCE)).finalize(
        WritePlanningRequest(
            actor_identity=TEST_ACTOR_IDENTITY,
            transaction_instant=instant_at("2024-06-01T00:00:00+00:00"),
            preference="optimistic",
            composed_writes=admitted_writes(_BALANCE, targets),
        )
    )
    return deferred_ranges(planned)


_SHAPES = pytest.mark.parametrize(
    "settled", [_bitemporal, _transaction_time_only], ids=["bitemporal", "transaction-time-only"]
)


def _formed(ranges: Sequence[DeferredRange]) -> list[tuple[object, ...]]:
    return [tuple(deferred.key_value for deferred in span.ranges) for span in form_spans(ranges)]


@_SHAPES
@pytest.mark.parametrize(
    ("objects", "sizes"),
    [(1, [1]), (31, [31]), (32, [32]), (33, [32, 1]), (65, [32, 32, 1])],
)
def test_a_run_forms_spans_of_at_most_the_bound(
    settled: Callable[..., tuple[DeferredRange, ...]], objects: int, sizes: list[int]
) -> None:
    ranges = settled(*range(1, objects + 1))
    formed = _formed(ranges)
    assert [len(span) for span in formed] == sizes
    assert [key for span in formed for key in span] == list(range(1, objects + 1))


def test_no_range_forms_no_span() -> None:
    assert _formed(()) == []


@_SHAPES
def test_a_range_of_an_object_the_open_span_holds_starts_the_next_span(
    settled: Callable[..., tuple[DeferredRange, ...]],
) -> None:
    # One finalization settles one range per object, so the repeat is another's.
    first, second = settled(1, 2)
    (repeated,) = settled(2)
    (third,) = settled(3)
    assert _formed((first, second, repeated, third)) == [(1, 2), (2, 3)]


def _keyed_by_label(deferred: DeferredRange) -> DeferredRange:
    """``deferred`` as though its Entity's family were keyed by ``label``."""
    key = deferred.read_key
    label = AttributeIdentity(key.entity.identity, "label")
    read_key = CoverageReadKey(key.entity, label, key.shared_lock)
    return replace(deferred, meaning=replace(deferred.meaning, read_key=read_key))


@pytest.mark.parametrize(
    "different",
    [
        lambda: _bitemporal(3, entity=ShareDoc)[0],
        lambda: _bitemporal(3, concurrency="locking")[0],
        lambda: _keyed_by_label(_bitemporal(3)[0]),
    ],
    ids=["another-entity", "another-lock", "another-key-attribute"],
)
def test_a_range_reading_differently_ends_the_open_span(
    different: Callable[[], DeferredRange],
) -> None:
    first, second = _bitemporal(1, 2)
    later = different()
    assert later.read_key != first.read_key
    (fourth,) = _bitemporal(4)
    assert _formed((first, second, later, fourth)) == [(1, 2), (3,), (4,)]


def test_ranges_reading_alike_share_a_span_whether_or_not_one_read_key_serves_them() -> None:
    (first,) = _bitemporal(1)
    (second,) = _bitemporal(2)
    assert first.read_key == second.read_key
    assert first.read_key is not second.read_key
    assert _formed((first, second)) == [(1, 2)]


def test_a_span_reads_by_its_first_ranges_read_key() -> None:
    (first,) = _bitemporal(1)
    (second,) = _bitemporal(2)
    (span,) = form_spans((first, second))
    assert span.read_key is first.read_key


def test_the_ready_writes_of_a_full_span_fit_one_write_group() -> None:
    # A span's ready writes execute as one group, which no span can overfill.
    ranges = spans_module._WRITES_PER_SPAN  # pyright: ignore[reportPrivateUsage] - the span bound
    writes = planner_module._WRITES_PER_GROUP  # pyright: ignore[reportPrivateUsage] - the group bound
    assert ranges <= writes


def _always(state: ObjectStateKey, read_at: int) -> bool:
    del state, read_at
    return True


class _Traced:
    """``held``'s answers, each request recorded in ``trace`` as it is asked
    for: a completion by the keys it completes, a coverage read by each key it
    names and how many parts. ``answers`` keeps each object's rows a read
    answered, and ``fail`` raises in place of the read it names, counting
    coverage reads from 1. What it records stays out of reach of the
    acquisition it hands out, which is a function."""

    def __init__(self, held: AcquireRows) -> None:
        self.trace: list[tuple[str, tuple[Any, ...]]] = []
        self.answers: list[PredecessorRows] = []
        self.fail: dict[int, BaseException] = {}
        self.reads = 0
        self.acquire = self._acquisition(held)

    def _acquisition(self, held: AcquireRows) -> AcquireRows:
        def acquire[Request: RowRequest, Result](
            request: Request, consumer: RowConsumer[Request, Result], /
        ) -> Result:
            self._asked(request)
            answer = held(request, consumer)
            self._record(answer)
            return answer

        return acquire

    def _asked(self, request: RowRequest) -> None:
        if isinstance(request, CompletionRequest):
            self.trace.append(("complete", tuple(row[0] for row in request.rows)))
            return
        assert isinstance(request, CoverageReadRequest)
        self.reads += 1
        self.trace.append(
            (
                "read",
                tuple((term.key_value, term.part_count) for term in request.terms),
            )
        )
        failure = self.fail.get(self.reads)
        if failure is not None:
            raise failure

    def _record(self, answer: object) -> None:
        if isinstance(answer, PredecessorRows):
            self.answers.append(answer)
        elif isinstance(answer, dict):
            by_key = cast("dict[object, PredecessorRows]", answer)
            self.answers.extend(by_key.values())


def _groups(written: WritePlan, acquire: AcquireRows, model: Metamodel = MODEL) -> SpanWriteGroups:
    (span,) = written.entries
    assert isinstance(span, AcquisitionSpan)
    return _span_groups(span, acquire, model)


def _span_groups(
    span: AcquisitionSpan, acquire: AcquireRows, model: Metamodel = MODEL
) -> SpanWriteGroups:
    planner = build_write_planner(bound_model(model))
    return write_groups(
        span,
        acquire_rows=acquire,
        current=_always,
        ownership=NO_TEMPORAL_WRITE_OWNERSHIP,
        audit=planner.audit_decoration(
            actor_identity=TEST_ACTOR_IDENTITY, transaction_instant=instant_at(AT.isoformat())
        ),
        payloads=planner.payloads,
    )


def _key(bound: WriteEffects) -> object:
    state = next(iter(bound.changed))
    assert isinstance(state, TemporalObjectStateKey)
    ((_name, value),) = state.object.primary_key
    return value


def _keys(group: WriteGroup) -> tuple[object, ...]:
    return tuple(_key(write) for write in group.writes)


def _members(groups: Sequence[WriteGroup]) -> list[SettledWrite]:
    return [write for group in groups for write in group.writes]


def _drained(groups: SpanWriteGroups, trace: list[tuple[str, tuple[Any, ...]]]) -> list[WriteGroup]:
    answered: list[WriteGroup] = []
    with groups:
        for each in groups:
            trace.append(("bind", _keys(each)))
            answered.append(each)
    return answered


def _closes(bound: SettledWrite) -> int:
    return sum(isinstance(step, PlannedClose) for step in bound.steps)


def _span(written: WritePlan) -> WritePlan:
    (span,) = written.entries
    assert isinstance(span, AcquisitionSpan) and len(span.ranges) > 1
    return written


def _fragmented(
    entity: type[Bitemporal],
    parts: Sequence[int],
    *,
    concurrency: ConcurrencyPreference = "optimistic",
) -> tuple[WritePlan, list[PredecessorRow]]:
    """One span of ``frag(k, parts[k - 1])`` for each object ``k``, beside every
    row the objects store."""
    writes = [write for key, count in enumerate(parts, 1) for write in frag(entity, key, count)]
    stored = [row for key, count in enumerate(parts, 1) for row in frag_rows(entity, key, count)]
    return _span(plan(writes, concurrency=concurrency)), stored


# --------------------------------------------------------------------------- #
# Readiness: the read finishing each range's parts, whatever it returned.     #
# --------------------------------------------------------------------------- #
def test_a_range_needing_nothing_binds_at_once_and_none_passes_an_earlier_unready_one() -> None:
    first, first_row = covered_target(ShareCols, 1)
    third, third_row = covered_target(ShareCols, 3)
    writes = [first, *frag(ShareCols, 2, 65), third, *frag(ShareCols, 4, 1)]
    stored = [first_row, *frag_rows(ShareCols, 2, 65), third_row, *frag_rows(ShareCols, 4, 1)]
    traced = _Traced(HeldRows(MODEL, stored, overlapping=True))
    written = _span(plan(writes, concurrency="locking"))
    bound = _drained(_groups(written, traced.acquire), traced.trace)
    # Readiness [0, 2, 0, 2]: the first executes alone before any read, and
    # the third waits behind the second's two reads, then joins its group.
    assert traced.trace == [
        ("complete", (1,)),
        ("complete", (3,)),
        ("bind", (1,)),
        ("read", ((2, 64),)),
        ("read", ((2, 1), (4, 1))),
        ("bind", (2, 3, 4)),
    ]
    assert [_keys(each) for each in bound] == [(1,), (2, 3, 4)]


def test_a_read_can_finish_one_range_while_it_reads_part_of_the_next() -> None:
    written, stored = _fragmented(ShareCols, (33, 33, 1))
    traced = _Traced(HeldRows(MODEL, stored, overlapping=True))
    bound = _members(_drained(_groups(written, traced.acquire), traced.trace))
    assert traced.trace == [
        ("read", ((1, 33), (2, 31))),
        ("bind", (1,)),
        ("read", ((2, 2), (3, 1))),
        ("bind", (2, 3)),
    ]
    # The second range binds both reads' rows: it closes every rectangle it
    # stores, those the first read found and those the second did.
    assert [_closes(each) for each in bound] == [2 * 33, 2 * 33, 2]


@pytest.mark.parametrize(
    ("parts", "reads"),
    [((63,), 1), ((64,), 1), ((65,), 2), ((63, 1), 1), ((64, 1), 2), ((32, 32), 1)],
)
def test_each_read_names_at_most_64_parts_of_the_span(parts: tuple[int, ...], reads: int) -> None:
    if len(parts) == 1:
        (count,) = parts
        written = plan(frag(ShareCols, 1, count))
        (alone,) = written.entries
        assert isinstance(alone, AcquisitionSpan) and len(alone.ranges) == 1
        stored = frag_rows(ShareCols, 1, count)
    else:
        written, stored = _fragmented(ShareCols, parts)
    traced = _Traced(HeldRows(MODEL, stored, overlapping=True))
    bound = _members(_drained(_groups(written, traced.acquire), traced.trace))
    named = [entry for entry in traced.trace if entry[0] == "read"]
    assert len(named) == reads
    assert all(sum(windows for _key, windows in terms) <= 64 for _kind, terms in named)
    # Every range closes every rectangle it stores, whatever read found it.
    for each, count in zip(bound, parts, strict=True):
        assert _closes(each) == 2 * count


@pytest.mark.parametrize("replaces", [False, True], ids=["amendment", "replacement"])
def test_a_range_whose_read_returned_nothing_binds_as_it_binds_alone(replaces: bool) -> None:
    # Object 2 stores only the rectangle it observed, so the read of the part
    # beyond it returns nothing for it: it is ready all the same.
    observed = rectangle(ShareCols, 2, 0, 2, 5)
    later = _reaching_past(observed, replaces=replaces)
    writes = [*frag(ShareCols, 1, 1), later]
    stored = [*frag_rows(ShareCols, 1, 1), observed]
    written = _span(plan(writes))
    traced = _Traced(HeldRows(MODEL, stored, overlapping=True))
    shared = _members(_drained(_groups(written, traced.acquire), traced.trace))
    assert traced.trace == [("read", ((1, 1), (2, 1))), ("bind", (1, 2))]
    alone = _members(
        _drained(_groups(plan([later]), HeldRows(MODEL, stored, overlapping=True)), [])
    )
    assert shared[1].steps == alone[0].steps
    openings = [_window(step) for step in shared[1].steps if isinstance(step, PlannedInsert)]
    # A replacement opens its state over the part no row held; an amendment
    # opens nothing past the rows it found.
    assert any(end == day(4) for _start, end in openings) is replaces


def _reaching_past(observed: PredecessorRow, *, replaces: bool) -> AdmittedWrite:
    prepared = prepare_instruction(
        KeyedWriteInstruction(
            "replaceUntil" if replaces else "amendUntil",
            ShareCols.identity.canonical,
            {"id": 2, "amount": 9, "label": "k2"} if replaces else {"id": 2, "amount": 9},
            day(0),
            day(4),
        ),
        write_preparation_of(MODEL),
        WIRE,
    )
    held = observation(ShareCols, observed)
    return admitted_write(prepared, held, held.key.object)


def _window(step: PlannedStep) -> tuple[object, object]:
    assert isinstance(step, PlannedInsert)
    (entry,) = step.entries
    cells = {identity.name: value for identity, value in entry.row.attributes.items()}
    return cells["validStart"], cells["validEnd"]


# --------------------------------------------------------------------------- #
# Each stored row reaches its own object's binding.                           #
# --------------------------------------------------------------------------- #


def test_a_row_one_read_returns_twice_reaches_its_binding_twice() -> None:
    # An Optimistic target write's caller states the row at its window's start.
    written = _span(plan([*frag(ShareCols, 1, 1), covered_target(ShareCols, 2)[0]]))
    start = rectangle(ShareCols, 2, 0, None, 0)
    held = HeldRows(MODEL, [*frag_rows(ShareCols, 1, 1), start, start], overlapping=True)
    with _groups(written, held) as groups:
        # Both are ready after the one read, so the later range's binding
        # fails the group the earlier one bound into.
        with raises_code(InternalError, CARDINALITY_CORRUPTION) as corrupt:
            next(groups)
        assert next(groups, None) is None
    assert "affected 2 row(s), expected 1" in str(corrupt.value)


def test_a_row_two_reads_both_return_is_bound_once() -> None:
    written, stored = _fragmented(ShareCols, (63, 2))
    traced = _Traced(_KeyedRows(stored))
    shared = _members(_drained(_groups(written, traced.acquire), traced.trace))
    # The second object's parts span both reads, and each returns all its rows.
    assert [entry for entry in traced.trace if entry[0] == "read"] == [
        ("read", ((1, 63), (2, 1))),
        ("read", ((2, 1),)),
    ]
    alone = _members(
        _drained(
            _groups(
                plan(frag(ShareCols, 2, 2)),
                HeldRows(MODEL, frag_rows(ShareCols, 2, 2), overlapping=True),
            ),
            [],
        )
    )
    assert shared[1].steps == alone[0].steps


@dataclass(slots=True)
class _KeyedRows:
    """A read answering every stored row of each object it names, whatever
    windows it names."""

    rows: Sequence[PredecessorRow]

    def __call__[Request: RowRequest, Result](
        self, request: Request, consumer: RowConsumer[Request, Result], /
    ) -> Result:
        assert isinstance(request, CoverageReadRequest)
        named = [term.key_value for term in request.terms]
        held = [row for row in self.rows if row.members["id"] in named]
        return HeldRows(MODEL, held)(request, consumer)


# --------------------------------------------------------------------------- #
# The failure encountered first propagates.                                   #
# --------------------------------------------------------------------------- #
class _Refused(Exception):
    pass


def test_a_later_ranges_retained_completion_fails_before_any_read() -> None:
    first, first_row = covered_target(ShareCols, 1)
    second, second_row = covered_target(ShareCols, 2)
    refused = _Refused()
    held = HeldRows(MODEL, [first_row, second_row], overlapping=True)

    def acquire[Request: RowRequest, Result](
        request: Request, consumer: RowConsumer[Request, Result], /
    ) -> Result:
        if isinstance(request, CompletionRequest) and request.rows[0][0] == 2:
            raise refused
        return held(request, consumer)

    written = _span(plan([first, *frag(ShareCols, 3, 1), second], concurrency="locking"))
    with pytest.raises(_Refused) as raised, _groups(written, acquire) as groups:
        next(groups)
    assert raised.value is refused
    assert [type(request) for request in held.requests] == [CompletionRequest]


# --------------------------------------------------------------------------- #
# However the scope ends, it holds none of the rows it read.                  #
# --------------------------------------------------------------------------- #
def _scope_frames(failure: BaseException) -> list[FrameType]:
    return frames(failure.__traceback__, module=spans_module.__file__)


def _three() -> tuple[WritePlan, list[PredecessorRow]]:
    """A span whose first read finishes the first range and reads part of the
    second, and whose second read finishes the second and the third."""
    return _fragmented(ShareCols, (1, 64, 1))


@pytest.mark.parametrize("leaves", ["exhaustion", "break", "raise"])
def test_a_scope_left_any_way_holds_none_of_the_rows_it_read(leaves: str) -> None:
    written, stored = _three()
    traced = _Traced(HeldRows(MODEL, stored, overlapping=True))
    groups = _groups(written, traced.acquire)
    bound: list[WriteGroup] = []
    with contextlib.suppress(_Refused), groups:
        for each in groups:
            bound.append(each)
            if leaves == "raise":
                raise _Refused
            if leaves == "break":
                break
    assert traced.answers
    assert not any(reaches([groups], rows) for rows in traced.answers)
    assert next(groups, None) is None
    # What the bound groups carry is the flush's, and stays usable.
    assert all(sum(isinstance(step, PlannedClose) for step in each.steps) for each in bound)


def test_a_failed_read_leaves_neither_the_scope_nor_its_frames_holding_an_earlier_reads_rows() -> (
    None
):
    written, stored = _three()
    traced = _Traced(HeldRows(MODEL, stored, overlapping=True))
    traced.fail[2] = DatabaseError(category="deadlock", native_code="40P01", message="deadlock")
    groups = _groups(written, traced.acquire)
    with pytest.raises(DatabaseError) as raised, groups:
        for _each in groups:
            pass
    # The first read's rows of the second range waited for the second read.
    partial = [rows for rows in traced.answers if rows.key(0) == 2]
    assert partial
    owned = _scope_frames(raised.value)
    assert owned
    assert not any(reaches([groups, *owned], rows) for rows in partial)


def test_a_failed_completion_leaves_neither_the_scope_nor_its_frames_holding_an_earlier_one() -> (
    None
):
    first, first_row = covered_target(ShareCols, 1)
    second, second_row = covered_target(ShareCols, 2)
    traced = _Traced(HeldRows(MODEL, [first_row, second_row], overlapping=True))
    refused = _Refused()

    def acquire[Request: RowRequest, Result](
        request: Request, consumer: RowConsumer[Request, Result], /
    ) -> Result:
        if isinstance(request, CompletionRequest) and request.rows[0][0] == 2:
            raise refused
        return traced.acquire(request, consumer)

    groups = _groups(_span(plan([first, second], concurrency="locking")), acquire)
    with pytest.raises(_Refused) as raised, groups:
        next(groups)
    assert len(traced.answers) == 1
    owned = _scope_frames(raised.value)
    assert owned
    assert not reaches([groups, *owned], traced.answers[0])


def test_a_failed_handoff_leaves_neither_the_scope_nor_its_frames_holding_the_reads_rows() -> None:
    written, stored = _three()
    # Every read answers every stored row, among them a row of an object no
    # read names, which is handed off after the rows of the span's objects.
    traced = _Traced(HeldRows(MODEL, [*stored, *frag_rows(ShareCols, 9, 1)]))
    groups = _groups(written, traced.acquire)
    with pytest.raises(AssertionError) as raised, groups:
        next(groups)
    owned = _scope_frames(raised.value)
    assert any(frame.f_code.co_name == "_transfer" for frame in owned)
    assert [rows for rows in traced.answers if rows.key(0) != 9]
    assert not any(reaches([groups, *owned], rows) for rows in traced.answers)


def test_a_failed_binding_leaves_neither_the_scope_nor_its_frames_holding_the_reads_rows() -> None:
    written = _span(plan([*frag(ShareCols, 1, 1), covered_target(ShareCols, 2)[0]]))
    start = rectangle(ShareCols, 2, 0, None, 0)
    traced = _Traced(HeldRows(MODEL, [*frag_rows(ShareCols, 1, 1), start, start], overlapping=True))
    groups = _groups(written, traced.acquire)
    with raises_code(InternalError, CARDINALITY_CORRUPTION) as raised, groups:
        for _each in groups:
            pass
    waiting = [rows for rows in traced.answers if rows.key(0) == 2]
    owned = _scope_frames(raised.value)
    assert waiting and owned
    assert not any(reaches([groups, *owned], rows) for rows in waiting)


def test_a_later_writes_failed_binding_leaves_no_frame_holding_the_earlier_bound_write(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bound: list[BoundRange] = []
    bind = DeferredRange.bind

    def binding(deferred: DeferredRange, *arguments: Any, **keywords: Any) -> BoundRange:
        bound.append(bind(deferred, *arguments, **keywords))
        return bound[-1]

    monkeypatch.setattr(DeferredRange, "bind", binding)
    written = _span(plan([*frag(ShareCols, 1, 1), covered_target(ShareCols, 2)[0]]))
    start = rectangle(ShareCols, 2, 0, None, 0)
    held = HeldRows(MODEL, [*frag_rows(ShareCols, 1, 1), start, start], overlapping=True)
    groups = _groups(written, held)
    with raises_code(InternalError, CARDINALITY_CORRUPTION) as raised, groups:
        next(groups)
    # Both ranges are ready after the one read: the earlier write was bound
    # and handed, as the settled write carrying its steps, to the group being
    # assembled when the later one failed; neither the assembly, the producer,
    # nor the scope keeps it.
    assert "affected 2 row(s), expected 1" in str(raised.value)
    (earlier,) = bound
    assembling = frames(raised.value.__traceback__, module=plan_module.__file__)
    assert any(frame.f_code.co_name == "from_writes" for frame in assembling)
    owners = [groups, *_scope_frames(raised.value), *assembling]
    assert not reaches(owners, earlier)
    assert not reaches(owners, earlier.steps)


def test_a_bound_deferred_write_is_a_settled_write_carrying_its_ranges_own_evidence() -> None:
    (write,) = frag(ShareCols, 1, 1)
    assert is_licensed_by(write, StateObserved)
    retained = write.authority.retained_observation
    source = ReadEvidence(ShareCols.identity, write.object_key, ParticipationToken(), retained)
    sourced = replace(write, authority=replace(write.authority, source_evidence=(source,)))
    written = plan([sourced])
    (deferred,) = deferred_ranges(written)
    held = HeldRows(MODEL, frag_rows(ShareCols, 1, 1), overlapping=True)
    with _groups(written, held) as groups:
        (group,) = groups
    (bound,) = group.writes
    # Binding settles the range into the write its group completes, which
    # carries the range's own evidence and its own steps, the group's alone.
    assert type(bound) is SettledWrite
    assert bound.source_evidence is deferred.source_evidence
    (carried,) = bound.source_evidence
    assert carried is source
    assert bound.steps is group.steps
    assert _key(bound) == 1


def test_a_deferred_write_a_planned_write_separates_binds_in_a_span_of_its_own() -> None:
    planned = plan([*frag(ShareCols, 1, 1), _inside_write(), *frag(ShareCols, 2, 1)])
    first, group, last = planned.entries
    assert isinstance(group, WriteGroup)
    for span in (first, last):
        assert isinstance(span, AcquisitionSpan) and len(span.ranges) == 1
    assert isinstance(last, AcquisitionSpan)
    held = HeldRows(MODEL, frag_rows(ShareCols, 2, 1), overlapping=True)
    with _span_groups(last, held) as groups:
        (bound,) = groups
    assert _keys(bound) == (2,)
    assert len(held.requests) == 1


def _inside_write() -> AdmittedWrite:
    """A write of object 9 its observation covers, so it binds at planning."""
    observed = rectangle(ShareCols, 9, 0, None, 0)
    prepared = prepare_instruction(
        KeyedWriteInstruction(
            "amendUntil", ShareCols.identity.canonical, {"id": 9, "amount": 9}, day(0), day(1)
        ),
        write_preparation_of(MODEL),
        WIRE,
    )
    held = observation(ShareCols, observed)
    return admitted_write(prepared, held, held.key.object)


# --------------------------------------------------------------------------- #
# Transaction-Time-Only ranges: each one part, its current row.               #
# --------------------------------------------------------------------------- #
class ShareLog(TxTemporal, table="share_log", namespace="parallax.execution.shared"):
    id: Attr[int] = attr(primary_key=True)
    amount: Attr[int]


_LOG_MODEL = model_of(DomainModel(ShareLog))


def _log_row(key: int) -> PredecessorRow:
    """Object ``key``'s current row, known from ``T0``."""
    return PredecessorRow(members={"id": key, "amount": key, "txStart": T0, "txEnd": INFINITY})


def _log_target(key: int, *, covered: bool = False) -> LicensedWrite[TxStartConditioned]:
    """A target write of object ``key`` stating ``T0``, beside, where
    ``covered``, the current row its Locking acquisition retained."""
    prepared = prepare_instruction(
        TargetWriteInstruction(
            "amend", ShareLog.identity.canonical, {"id": key, "amount": 7}, if_tx_start=T0
        ),
        write_preparation_of(_LOG_MODEL),
        WIRE,
    )
    assert isinstance(prepared, PreparedTargetInstruction)
    families = inheritance_facet_of(_LOG_MODEL)
    write = target_write(prepared, families)
    assert is_licensed_by(write, TxStartConditioned)
    if not covered:
        return write
    view = families.entity(ShareLog.identity)
    shape = temporal_facet_of(_LOG_MODEL).shape(ShareLog.identity)
    assert view is not None and shape is not None
    stored = _log_row(key)
    state = TemporalObjectStateKey(
        ObjectKey(ShareLog.identity, (("id", key),)), milestone_edge(shape, stored, None)
    )
    row = positional_row(view.member_selection.shape, stored.members, absent=ABSENT)
    starting_row = RetainedStartingRow(state, 0, row, None)
    return replace(write, authority=replace(write.authority, starting_row=starting_row))


def _log_plan(
    writes: Sequence[AdmittedWrite], *, concurrency: ConcurrencyPreference = "optimistic"
) -> WritePlan:
    return build_write_planner(bound_model(_LOG_MODEL)).finalize(
        WritePlanningRequest(
            actor_identity=TEST_ACTOR_IDENTITY,
            transaction_instant=instant_at(AT.isoformat()),
            preference=concurrency,
            composed_writes=admitted_writes(_LOG_MODEL, list(writes)),
        )
    )


def _closed(bound: SettledWrite) -> tuple[object, ...]:
    (close,) = (step for step in bound.steps if isinstance(step, PlannedClose))
    assert isinstance(close.target, MilestoneTarget)
    return close.target.key_values


def test_transaction_time_only_ranges_share_one_read_naming_each_current_row_once() -> None:
    written = _span(_log_plan([_log_target(key) for key in (1, 2, 3)]))
    # The rows arrive in another order than the read names their objects.
    traced = _Traced(
        HeldRows(_LOG_MODEL, [_log_row(3), _log_row(1), _log_row(2)], overlapping=True)
    )
    shared = _members(_drained(_groups(written, traced.acquire, _LOG_MODEL), traced.trace))
    assert traced.trace == [("read", ((1, 1), (2, 1), (3, 1))), ("bind", (1, 2, 3))]
    assert [_closed(bound) for bound in shared] == [(1,), (2,), (3,)]
    alone = _members(
        _drained(
            _groups(
                _log_plan([_log_target(2)]),
                HeldRows(_LOG_MODEL, [_log_row(2)], overlapping=True),
                _LOG_MODEL,
            ),
            [],
        )
    )
    assert shared[1].steps == alone[0].steps


def test_a_covered_range_needs_no_read_and_never_passes_an_uncovered_one() -> None:
    writes = [
        _log_target(1, covered=True),
        _log_target(2),
        _log_target(3, covered=True),
        _log_target(4),
    ]
    written = _span(_log_plan(writes, concurrency="locking"))
    traced = _Traced(HeldRows(_LOG_MODEL, [_log_row(2), _log_row(4)], overlapping=True))
    _drained(_groups(written, traced.acquire, _LOG_MODEL), traced.trace)
    # The covered first range runs before anything is read; the covered third
    # waits for the read the second needs, and runs with it once it succeeded.
    assert traced.trace == [
        ("complete", (1,)),
        ("complete", (3,)),
        ("bind", (1,)),
        ("read", ((2, 1), (4, 1))),
        ("bind", (2, 3, 4)),
    ]


def test_a_full_spans_current_rows_share_one_read_each_one_part() -> None:
    keys = range(1, 33)
    written = _span(_log_plan([_log_target(key) for key in keys]))
    traced = _Traced(HeldRows(_LOG_MODEL, [_log_row(key) for key in keys], overlapping=True))
    shared = _members(_drained(_groups(written, traced.acquire, _LOG_MODEL), traced.trace))
    named = [terms for kind, terms in traced.trace if kind == "read"]
    assert named == [tuple((key, 1) for key in keys)]
    assert [_closed(each) for each in shared] == [(key,) for key in keys]


def test_a_range_its_read_found_nothing_for_is_ready_and_binds_to_no_row() -> None:
    written = _span(_log_plan([_log_target(1), _log_target(2)]))
    traced = _Traced(HeldRows(_LOG_MODEL, [_log_row(1)], overlapping=True))
    with (
        raises_code(WritePreconditionError, WRITE_PRECONDITION_FAILED) as failed,
        _groups(written, traced.acquire, _LOG_MODEL) as groups,
    ):
        next(groups)
    # One read named both objects; the second, ready once it succeeded, bound
    # to the absence of its row and failed as its caller's precondition.
    assert traced.trace == [("read", ((1, 1), (2, 1)))]
    assert "key={'id': 2}" in str(failed.value)


def test_a_failed_read_binds_no_range_still_waiting_for_it() -> None:
    written, stored = _fragmented(ShareCols, (64, 1))
    traced = _Traced(HeldRows(MODEL, stored, overlapping=True))
    traced.fail[2] = DatabaseError(category="deadlock", native_code="40P01", message="deadlock")
    with pytest.raises(DatabaseError), _groups(written, traced.acquire) as groups:
        for each in groups:
            traced.trace.append(("bind", _keys(each)))
    assert traced.trace == [("read", ((1, 64),)), ("bind", (1,)), ("read", ((2, 1),))]
