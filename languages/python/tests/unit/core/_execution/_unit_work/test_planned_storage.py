"""What a finalized Write Plan retains (m-unit-work, Docker-free): what a
producer produced for one settled write, never the producer.
"""

from __future__ import annotations

import datetime as dt
from decimal import Decimal
from types import FunctionType, MethodType

import pytest

from parallax.conformance import models
from parallax.conformance.scripted_clock import FixedClock
from parallax.core import inheritance
from parallax.core._execution._planning import build_write_planner
from parallax.core._execution._unit_work.instructions import (
    PreparedTargetWrite,
    TargetWriteInstruction,
    prepare_typed_write,
    prepare_wire_write,
)
from parallax.core._execution._unit_work.ranges import DeferredTemporalRange
from parallax.core._execution._unit_work.strategy import (
    AuditDecoration,
    AuditStrategy,
    BatchingStrategy,
    ConcurrencyStrategy,
)
from parallax.core._execution._unit_work.write_items import target_write
from parallax.core._execution._unit_work.write_settlement import (
    WritePlanCompiler,  # producer-reach regression only
)
from parallax.core._formation_profile import BUILTIN_MANIFEST
from parallax.core.metamodel import FacetKey
from parallax.core.model_formation import ModelCompilerRequirement
from parallax.core.temporal_read import TimeInterval
from parallax.core.temporal_write.expansion import PredecessorExpander
from parallax.core.unit_work import (
    KeyedWriteInstruction,
    SystemClock,
    TransactionInstant,
    VersionArithmetic,
    WritePlanner,
    WritePlanningRequest,
)
from parallax.core.write_payload import LayoutPayloadPreparer
from parallax.core.write_plan import (
    WritePlan,
)
from tests._support.clock_probes import CountingClock, inert_instant
from tests._support.planner_probes import TEST_ACTOR_IDENTITY, admitted_writes
from tests.unit._gc_reachability import reachable_objects
from tests.unit.core._execution._unit_work._ownership_support import OpenedRows

_MODELS = models.load_models()
_BALANCE = _MODELS["balance"]
_POSITION = _MODELS["position"]
_OPENED = dt.datetime(2024, 1, 1, tzinfo=dt.UTC)
_JAN, _MAR = (dt.datetime(2026, month, 1, tzinfo=dt.UTC) for month in (1, 3))


# --------------------------------------------------------------------------- #
# Finalizing: a Write Plan may retain what a producer produced for one        #
# settled write, never the producer.                                          #
# --------------------------------------------------------------------------- #
_PRODUCER_CLASSES = (
    TransactionInstant,
    FixedClock,
    SystemClock,
    WritePlanner,
    WritePlanCompiler,
    PredecessorExpander,
    BatchingStrategy,
    ConcurrencyStrategy,
    AuditStrategy,
    type(_BALANCE),
)

_COMPILED_FACET_KEYS: tuple[FacetKey[object], ...] = tuple(
    entry.compiler.facet_key
    for entry in BUILTIN_MANIFEST.entries
    if isinstance(entry.compiler, ModelCompilerRequirement)
)
"""Every key an accepted built-in model installs a compiled facet under.

Each key carries its owner's own decision procedure for "is this value my
facet?", which recognizes a facet no shape distinguishes.
"""


def _is_producer(value: object) -> bool:
    return isinstance(value, _PRODUCER_CLASSES) or any(
        key.accepts(value) for key in _COMPILED_FACET_KEYS
    )


def _reachable_from_plan(plan: WritePlan) -> list[object]:
    """Everything a plan's segments and execution units reach, every deferred
    range's description included."""
    return [
        value for held in (*plan.steps.segments, *plan.units) for value in reachable_objects(held)
    ]


def test_every_facet_an_accepted_model_carries_counts_as_a_producer() -> None:
    # A plan may reach nothing `_is_producer` recognizes, so every facet an
    # accepted model carries, and the clock, must count as a producer, while
    # what either produced for one settled write must not.
    facets = [_BALANCE.facet(key) for key in _COMPILED_FACET_KEYS]
    assert len(facets) == len(_COMPILED_FACET_KEYS) > 1

    for facet in facets:
        assert _is_producer(facet)
    assert _is_producer(_BALANCE)
    entity = _BALANCE.entities[0]
    assert not _is_producer(inheritance.view(_BALANCE).entity(entity.identity))
    assert not _is_producer(VersionArithmetic(initial=1, increment=1))
    instant = inert_instant()
    assert _is_producer(instant.clock)
    assert not _is_producer(instant.value())


def test_a_deferred_range_retains_finalized_data_and_neither_producer_nor_ownership() -> None:
    # A deferred range is bound at execution, under the ownership the attempt
    # holds then and the audit the unit of work supplies; its plan entry keeps
    # the finalized meaning and the resolved instant, and nothing that could
    # decide again — no clock, strategy, planner, live ownership, actor, or a
    # bound method or closure reaching one.
    clock = CountingClock([dt.datetime(2024, 6, 1, tzinfo=dt.UTC)])
    ownership = OpenedRows(frozenset())
    prepared = prepare_wire_write(
        TargetWriteInstruction(
            "amendUntil",
            "Position",
            {"id": 1, "value": "9.00"},
            if_tx_start=_OPENED,
            valid_from=_JAN,
            until=_MAR,
        ),
        _POSITION,
    )
    assert isinstance(prepared, PreparedTargetWrite)
    plan = build_write_planner(_POSITION).finalize(
        WritePlanningRequest(
            actor_identity=TEST_ACTOR_IDENTITY,
            transaction_instant=TransactionInstant(clock),
            concurrency="optimistic",
            buffered_writes=admitted_writes(
                _POSITION, [target_write(prepared, inheritance.view(_POSITION))]
            ),
            ownership=ownership,
        )
    )
    (unit,) = plan.units
    assert isinstance(unit.deferred, DeferredTemporalRange)
    walked = _reachable_from_plan(plan)
    assert not [value for value in walked if _is_producer(value)]
    assert not [value for value in walked if isinstance(value, OpenedRows | AuditDecoration)]
    assert all(value is not TEST_ACTOR_IDENTITY for value in walked)
    assert not [value for value in walked if isinstance(value, MethodType | FunctionType)]
    # The walk descended into the description: its resolved instant and the
    # requested window are both reached.
    assert dt.datetime(2024, 6, 1, tzinfo=dt.UTC) in walked
    assert any(isinstance(value, TimeInterval) for value in walked)
    assert clock.calls == 1


def test_a_pending_opening_settles_through_no_retained_producer_and_prepares_no_payload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # A pending insertion's surviving parts are settled by the one temporal
    # expansion every range uses, which the plan does not keep, and what they
    # persist is prepared only when each statement is lowered.
    def refuse(*_args: object) -> object:
        raise AssertionError("a payload was prepared before its statement was lowered")

    monkeypatch.setattr(LayoutPayloadPreparer, "row", refuse)
    monkeypatch.setattr(LayoutPayloadPreparer, "assignments", refuse)
    writes = [
        prepare_typed_write(
            KeyedWriteInstruction(
                "insert",
                "Position",
                ({"id": 1, "acctNum": "A", "value": Decimal("1.00")},),
                valid_from=_JAN,
            ),
            _POSITION,
        ),
        prepare_typed_write(
            KeyedWriteInstruction(
                "amendUntil",
                "Position",
                ({"id": 1, "value": Decimal("2.00")},),
                valid_from=_JAN,
                until=_MAR,
            ),
            _POSITION,
        ),
    ]
    plan = build_write_planner(_POSITION).finalize(
        WritePlanningRequest(
            actor_identity=TEST_ACTOR_IDENTITY,
            transaction_instant=inert_instant(),
            concurrency="optimistic",
            buffered_writes=admitted_writes(_POSITION, writes),
        )
    )
    assert len(list(plan.steps)) == 2
    assert not [value for value in _reachable_from_plan(plan) if _is_producer(value)]
