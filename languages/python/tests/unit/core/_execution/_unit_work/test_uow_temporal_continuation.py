"""A temporal source's continuation across this attempt's own completed writes,
at the unit-of-work seam (`m-unit-work` *Observation ownership and lifetime*,
*Write Groups complete before later work runs*).

Each case retains one observation of a stored Bitemporal row as a read's
retention does, buffers writes through it, and flushes them over simulated
step execution that changes the stored rows. What it grades is which rows the
attempt holds for the source once each write completes — exactly the complete
state each execution stored, captured as its payload was demanded — that a
later write through the source binds to them without reading anything, and
that nothing a failed group staged, a pre-commit flush executed, or a
collected observation reached stays held.
"""

from __future__ import annotations

import datetime as dt
import gc
from collections.abc import Callable
from decimal import Decimal
from typing import Any, Final

import pytest

from parallax.conformance._simulated_write_steps import SimulatedWriteSteps
from parallax.conformance.scripted_clock import FixedClock
from parallax.conformance.simulated_temporal_store import SimulatedTemporalStore
from parallax.core import opt_lock
from parallax.core._execution._planning import build_write_planner
from parallax.core._execution._transaction._lifetime import TxnAttemptLifetime
from parallax.core._execution._unit_work import ranges
from parallax.core._execution._unit_work import uow as uow_module
from parallax.core._execution._unit_work._write_ownership import WriteOwnership
from parallax.core._execution._unit_work.acquisition import (
    CoverageReadRequest,
    CoverageTerm,
    RowConsumer,
    RowRequest,
    consume_coverage,
)
from parallax.core._execution._unit_work.instructions import (
    PreparedKeyedInstruction,
    PreparedTargetInstruction,
    prepare_wire_write,
)
from parallax.core._execution._unit_work.write_runner import (
    _CurrentRowCapture,  # pyright: ignore[reportPrivateUsage] - the capture a running group builds
)
from parallax.core.base import INFINITY
from parallax.core.dialect import POSTGRES
from parallax.core.entity._model import model_of
from parallax.core.metamodel import AttributeIdentity, entity_by_name
from parallax.core.unit_work import (
    Concurrency,
    KeyedWriteInstruction,
    RetainedObservation,
    RollbackOnlyError,
    TargetWriteInstruction,
    TransactionSettings,
    UnitOfWork,
    UnitOfWorkError,
    WriteEvidenceError,
    admitted_write,
    object_key,
)
from parallax.core.write_plan import ObjectKey, PredecessorRow, TemporalObservation
from parallax.core.write_plan.plan import BoundRange
from tests._support.planner_probes import (
    NO_COUNTED_STEPS,
    TEST_ACTOR_IDENTITY,
    retained_observation,
)
from tests.unit._where_position_model import WHERE_POSITION_META
from tests.unit.core._execution._reach_support import frames, reaches

_META: Final = model_of(WHERE_POSITION_META)
_FOUND = entity_by_name(_META, "WherePosition")
assert _FOUND is not None
_ENTITY: Final = _FOUND
_T0: Final = dt.datetime(2023, 12, 1, tzinfo=dt.UTC)
_NOW: Final = dt.datetime(2024, 6, 15, tzinfo=dt.UTC)
_JAN, _FEB, _MAR, _APR, _JUN, _JUL, _AUG, _SEP, _OCT, _NOV = (
    dt.datetime(2024, month, 1, tzinfo=dt.UTC) for month in (1, 2, 3, 4, 6, 7, 8, 9, 10, 11)
)
_HUNDRED: Final = Decimal("100.00")

type _Stored = tuple[object, object, object, object, object]


def _write(
    valid_from: dt.datetime, until: dt.datetime | None = None, **members: object
) -> PreparedKeyedInstruction:
    verb = "amend" if until is None else "amendUntil"
    prepared = prepare_wire_write(
        KeyedWriteInstruction(
            verb, "WherePosition", ({"id": 1, **members},), valid_from=valid_from, until=until
        ),
        _META,
    )
    assert isinstance(prepared, PreparedKeyedInstruction)
    return prepared


_KEY: Final[ObjectKey] = object_key(_write(_JAN), _META)  # pyright: ignore[reportAssignmentType]


class _Session:
    """One attempt over a store holding WherePosition 1 from January, as one
    row or as rows ending at each of ``ends``, recording every row acquisition
    it asks for."""

    def __init__(
        self,
        *,
        concurrency: Concurrency = "optimistic",
        execute: Callable[[SimulatedWriteSteps], Any] | None = None,
        ends: tuple[object, ...] = (INFINITY,),
    ) -> None:
        self.store = SimulatedTemporalStore()
        self.seeded = [
            {
                "id": 1,
                "acctNum": "A",
                "value": _HUNDRED,
                "validStart": start,
                "validEnd": end,
                "txStart": _T0,
                "txEnd": INFINITY,
            }
            for start, end in zip((_JAN, *ends[:-1]), ends, strict=True)
        ]
        self.store.seed_fixtures(_META, _ENTITY, self.seeded)
        self.simulated = SimulatedWriteSteps(
            build_write_planner(_META).payloads, _META, POSTGRES, store=self.store
        )
        self.requests: list[RowRequest] = []
        self.uow = UnitOfWork(
            settings=TransactionSettings(concurrency=concurrency),
            lifetime=TxnAttemptLifetime(),
            clock=FixedClock(_NOW),
            meta=_META,
            execute_write_steps=self.simulated if execute is None else execute(self.simulated),
            execute_counted_step=NO_COUNTED_STEPS,
            acquire_rows=self._acquire,
            planner=build_write_planner(_META),
            actor_identity=TEST_ACTOR_IDENTITY,
            evidence_policy_for=opt_lock.view(_META).required_key,
        )

    def _acquire[Request: RowRequest, Result](
        self, request: Request, consumer: RowConsumer[Request, Result], /
    ) -> Result:
        self.requests.append(request)
        return self.store.acquisition(_META)(request, consumer)

    def observed(self) -> RetainedObservation:
        """A fresh retained observation of the row WherePosition 1 was seeded
        with from January."""
        observation = TemporalObservation(predecessor=PredecessorRow(members=self.seeded[0]))
        return self.uow.retain(retained_observation(_write(_JAN), _META, observation))

    def flush(self, *writes: tuple[PreparedKeyedInstruction, RetainedObservation]) -> None:
        for prepared, observation in writes:
            self.uow.buffer(admitted_write(prepared, observation, observation.key.object))
        with self.store.transaction(rollback=False):
            self.uow.flush(trigger="read_dependency")

    @property
    def ownership(self) -> WriteOwnership:
        ownership = self.uow._admission.ownership  # pyright: ignore[reportPrivateUsage] - what the attempt holds
        assert isinstance(ownership, WriteOwnership)
        return ownership

    def held(self) -> list[_Stored]:
        return sorted(
            (_described(row) for row in self.ownership.current_rows(_KEY, None)),
            key=_by_start,
        )

    def stored(self) -> list[_Stored]:
        covered = self.store.acquisition(_META)(
            CoverageReadRequest(
                entity=_ENTITY,
                key_attribute=AttributeIdentity(_ENTITY.identity, "id"),
                terms=(CoverageTerm(1, ()),),
                locking=False,
            ),
            consume_coverage,
        )
        assert covered is not None
        return sorted(
            (
                _described(
                    PredecessorRow.over_row(
                        covered.selection,
                        covered.rows[index],
                        covered.document(index),
                        covered.absent,
                    )
                )
                for index in range(len(covered))
            ),
            key=_by_start,
        )


def _described(row: PredecessorRow) -> _Stored:
    members = row.members
    return (
        members["validStart"],
        members["validEnd"],
        members["txStart"],
        members["acctNum"],
        members["value"],
    )


def _by_start(stored: _Stored) -> dt.datetime:
    start = stored[0]
    assert isinstance(start, dt.datetime)
    return start


@pytest.mark.parametrize("concurrency", ["optimistic", "locking"])
def test_a_continuing_source_binds_to_the_rows_its_completed_writes_stored_without_a_read(
    concurrency: Concurrency,
) -> None:
    session = _Session(concurrency=concurrency)
    source = session.observed()
    session.flush((_write(_FEB, _APR, acctNum="O"), source))
    # Every row the write derived from the observed state is held, exactly as
    # its execution stored it.
    assert session.held() == session.stored()
    assert len(session.held()) == 3
    session.flush((_write(_FEB, _MAR, value="150.00"), source))
    session.flush((_write(_JUN, _AUG, value="175.00"), source))
    assert session.requests == []
    assert session.stored() == [
        (_JAN, _FEB, _NOW, "A", _HUNDRED),
        (_FEB, _MAR, _NOW, "O", Decimal("150.00")),
        (_MAR, _APR, _NOW, "O", _HUNDRED),
        (_APR, _JUN, _NOW, "A", _HUNDRED),
        (_JUN, _AUG, _NOW, "A", Decimal("175.00")),
        (_AUG, INFINITY, _NOW, "A", _HUNDRED),
    ]
    assert session.held() == session.stored()


def test_repeated_writes_through_one_source_hold_its_current_rows_and_no_history() -> None:
    session = _Session()
    source = session.observed()
    for round_ in range(40):
        start, end = (_JUN, _JUL) if round_ % 2 else (_JUL, _AUG)
        session.flush((_write(start, end, value=f"{round_ + 1}.00"), source))
    assert session.requests == []
    stored = session.stored()
    assert session.held() == stored
    assert len(stored) == 4
    ownership = session.ownership
    contributions = ownership._contributions  # pyright: ignore[reportPrivateUsage] - the reverse view's size
    (origin,) = ownership._origins.values()  # pyright: ignore[reportPrivateUsage] - the one origin's geometry
    assert len(contributions) == len(origin.lineage.contributions) == len(stored)


def test_a_composed_range_binds_the_rows_held_for_its_source_without_comparing_them(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = _Session()
    source = session.observed()
    for round_ in range(20):
        end = _FEB + dt.timedelta(days=40 - round_)
        session.flush((_write(_FEB, end, value=f"{round_ + 1}.00"), source))
    held = len(session.held())
    compared = 0
    overlapping = ranges._overlapping  # pyright: ignore[reportPrivateUsage] - the comparison counted

    def counted(*predecessors: Any) -> bool:
        nonlocal compared
        compared += 1
        return overlapping(*predecessors)

    monkeypatch.setattr(ranges, "_overlapping", counted)
    session.uow.buffer(admitted_write(_write(_FEB, acctNum="Z"), source, source.key.object))
    session.uow.buffer(
        admitted_write(_write(_FEB, _MAR, value="150.00"), source, source.key.object)
    )
    _flush_buffered(session)
    assert session.requests == []
    assert compared <= held
    stored = session.stored()
    assert session.held() == stored
    assert [row[3] for row in stored] == ["A", *["Z"] * (len(stored) - 1)]
    assert stored[1][4] == Decimal("150.00")


def test_a_pre_commit_flush_which_no_submission_follows_records_nothing_for_continuation() -> None:
    session = _Session()
    source = session.observed()
    session.flush((_write(_FEB, _APR, acctNum="O"), source))
    contributions = session.ownership._contributions  # pyright: ignore[reportPrivateUsage] - what lineage records
    recorded = set(contributions)
    session.uow.buffer(
        admitted_write(_write(_FEB, _MAR, value="150.00"), source, source.key.object)
    )
    with session.store.transaction(rollback=False):
        session.uow.flush(trigger="pre_commit")
    # The pre-commit write bound to the rows the earlier flush left, reading
    # nothing, and recorded nothing new for a later write to continue from.
    assert session.requests == []
    assert set(contributions) == recorded
    assert (_FEB, _MAR, _NOW, "O", Decimal("150.00")) in session.stored()


@pytest.mark.parametrize("trigger", ["read_dependency", "pre_commit"])
def test_a_deferred_range_records_for_continuation_only_where_a_submission_follows(
    trigger: Any,
) -> None:
    # The source observed the row ending in September; the write reaches the
    # stored row past it, so its range binds at execution.
    session = _Session(ends=(_SEP, INFINITY))
    source = session.observed()
    session.uow.buffer(admitted_write(_write(_FEB, acctNum="O"), source, source.key.object))
    with session.store.transaction(rollback=False):
        session.uow.flush(trigger=trigger)
    assert [type(request) for request in session.requests] == [CoverageReadRequest]
    ownership = session.ownership
    if trigger == "pre_commit":
        # Bound under the concluding view, it describes nothing a source
        # could continue from: no origin, no contribution, no held row.
        assert ownership._origins == {}  # pyright: ignore[reportPrivateUsage] - nothing recorded
        assert ownership._contributions == {}  # pyright: ignore[reportPrivateUsage] - nothing recorded
        assert session.held() == []
        assert ownership.continues(source, _MAR) is None
    else:
        assert session.held() == session.stored()
        assert ownership.continues(source, _MAR)


def test_a_failed_deferred_groups_capture_is_released_and_its_frames_keep_no_bound_range(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    released: list[_CurrentRowCapture] = []
    release = _CurrentRowCapture.release
    bound: list[BoundRange] = []
    bind = ranges._bind_range  # pyright: ignore[reportPrivateUsage] - the binding every deferred range takes

    def releasing(capture: _CurrentRowCapture) -> None:
        released.append(capture)
        release(capture)

    def binding(*arguments: Any, **keywords: Any) -> BoundRange:
        bound.append(bind(*arguments, **keywords))
        return bound[-1]

    def failing(simulated: SimulatedWriteSteps) -> Callable[..., tuple[object, ...]]:
        def execute(*arguments: Any, **keywords: Any) -> tuple[object, ...]:
            simulated(*arguments, **keywords)
            raise RuntimeError("the group failed")

        return execute

    monkeypatch.setattr(_CurrentRowCapture, "release", releasing)
    monkeypatch.setattr(ranges, "_bind_range", binding)
    session = _Session(execute=failing, ends=(_SEP, INFINITY))
    source = session.observed()
    with pytest.raises(RuntimeError, match="the group failed") as raised:
        session.flush((_write(_FEB, acctNum="O"), source))
    ((range_,),) = [bound]
    (capture,) = released
    # The capture staged the rows the group's payloads stored, and dropped
    # them with every description once the group failed.
    assert capture._outputs == {}  # pyright: ignore[reportPrivateUsage] - what the capture still holds
    assert capture._staged == {}  # pyright: ignore[reportPrivateUsage] - what the capture still holds
    owned = frames(raised.value.__traceback__, module=uow_module.__file__)
    assert owned
    assert not reaches(owned, range_)
    assert session.held() == []
    assert session.ownership.continues(source, _MAR) is None


def test_a_group_whose_steps_fail_after_their_payloads_were_demanded_holds_nothing() -> None:
    def failing(simulated: SimulatedWriteSteps) -> Callable[..., tuple[object, ...]]:
        def execute(*arguments: Any, **keywords: Any) -> tuple[object, ...]:
            simulated(*arguments, **keywords)
            raise RuntimeError("the group failed")

        return execute

    session = _Session(execute=failing)
    source = session.observed()
    with pytest.raises(RuntimeError, match="the group failed"):
        session.flush((_write(_FEB, _APR, acctNum="O"), source))
    assert session.ownership.continues(source, _MAR) is None
    assert session.held() == []
    with pytest.raises(RollbackOnlyError):
        session.uow.read(lambda: None)


def test_a_group_answering_keys_it_did_not_allocate_holds_nothing() -> None:
    def answering(simulated: SimulatedWriteSteps) -> Callable[..., tuple[object, ...]]:
        def execute(*arguments: Any, **keywords: Any) -> tuple[object, ...]:
            return (*simulated(*arguments, **keywords), 7)

        return execute

    session = _Session(execute=answering)
    source = session.observed()
    with pytest.raises(UnitOfWorkError):
        session.flush((_write(_FEB, _APR, acctNum="O"), source))
    assert session.ownership.continues(source, _MAR) is None
    assert session.held() == []


def test_rows_held_for_a_source_nothing_reaches_any_longer_are_released() -> None:
    # The settled write alone kept the observation live through its
    # completion; once it is gone, so is everything held for that observation.
    session = _Session()
    session.flush((_write(_FEB, _APR, acctNum="O"), session.observed()))
    gc.collect()
    ownership = session.ownership
    assert ownership._origins == {}  # pyright: ignore[reportPrivateUsage] - nothing is left
    assert ownership._contributions == {}  # pyright: ignore[reportPrivateUsage] - nothing is left
    assert session.held() == []


def _target(
    valid_from: dt.datetime, until: dt.datetime, tx_start: dt.datetime, **members: object
) -> PreparedTargetInstruction:
    prepared = prepare_wire_write(
        TargetWriteInstruction(
            "amendUntil",
            "WherePosition",
            {"id": 1, **members},
            if_tx_start=tx_start,
            valid_from=valid_from,
            until=until,
        ),
        _META,
    )
    assert isinstance(prepared, PreparedTargetInstruction)
    return prepared


def _flush_buffered(session: _Session) -> None:
    with session.store.transaction(rollback=False):
        session.uow.flush(trigger="read_dependency")


def test_a_caller_beside_a_continuing_source_states_the_start_of_the_row_held_there() -> None:
    # The source's own rectangle is gone; the caller's disjoint window starts
    # in a row the source's completed write produced, whose own start alone
    # admits the caller beside the source.
    session = _Session()
    source = session.observed()
    session.flush((_write(_FEB, _APR, acctNum="O"), source))
    session.uow.buffer(
        admitted_write(_write(_FEB, _MAR, value="150.00"), source, source.key.object)
    )
    with pytest.raises(WriteEvidenceError) as refused:
        session.uow.buffer_target(_target(_JUN, _AUG, _T0, value="175.00"))
    assert refused.value.code == "write-evidence-already-claimed"
    session.uow.buffer_target(_target(_JUN, _AUG, _NOW, value="175.00"))
    _flush_buffered(session)
    assert session.stored() == [
        (_JAN, _FEB, _NOW, "A", _HUNDRED),
        (_FEB, _MAR, _NOW, "O", Decimal("150.00")),
        (_MAR, _APR, _NOW, "O", _HUNDRED),
        (_APR, _JUN, _NOW, "A", _HUNDRED),
        (_JUN, _AUG, _NOW, "A", Decimal("175.00")),
        (_AUG, INFINITY, _NOW, "A", _HUNDRED),
    ]


def test_a_caller_of_a_continuing_sources_window_is_one_operation_from_the_row_held_there() -> None:
    session = _Session()
    source = session.observed()
    session.flush((_write(_FEB, _APR, acctNum="O"), source))
    session.uow.buffer(
        admitted_write(_write(_JUN, _AUG, value="175.00"), source, source.key.object)
    )
    session.uow.buffer_target(_target(_JUN, _AUG, _NOW, acctNum="T"))
    _flush_buffered(session)
    assert (_JUN, _AUG, _NOW, "T", Decimal("175.00")) in session.stored()


def test_a_caller_beside_a_continuing_source_past_the_rows_held_states_the_stored_start() -> None:
    # The source observed the row ending in September; the stored row after
    # it is no row the attempt holds, so the caller states its own start.
    session = _Session(ends=(_SEP, INFINITY))
    source = session.observed()
    session.flush((_write(_FEB, _APR, acctNum="O"), source))
    session.uow.buffer(
        admitted_write(_write(_FEB, _MAR, value="150.00"), source, source.key.object)
    )
    session.uow.buffer_target(_target(_OCT, _NOV, _T0, value="175.00"))
    _flush_buffered(session)
    assert session.stored()[-3:] == [
        (_SEP, _OCT, _NOW, "A", _HUNDRED),
        (_OCT, _NOV, _NOW, "A", Decimal("175.00")),
        (_NOV, INFINITY, _NOW, "A", _HUNDRED),
    ]
