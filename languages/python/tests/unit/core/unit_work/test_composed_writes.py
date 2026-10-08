"""How a temporal object's observed writes compose at admission and what the
composition settles into, driven at the planner seam without a database."""

from __future__ import annotations

import datetime as dt
from decimal import Decimal

import pytest

from parallax.core import temporal_read
from parallax.core.base import INFINITY
from parallax.core.execution._planning import build_write_planner
from parallax.core.metamodel import EntityIdentity
from parallax.core.unit_work import (
    BufferItem,
    KeyedMutation,
    KeyedWrite,
    RetainedObservation,
    WritePlanningRequest,
    buffered_write,
)
from parallax.core.unit_work.instructions import prepare_wire_write
from parallax.core.unit_work.materialized import ComposedTemporalWrite, ObservedKeyedWrite
from parallax.core.unit_work.write_planner import compose_writes
from parallax.core.write_plan import (
    SUPERSEDED,
    TERMINATED,
    ObjectKey,
    PlannedClose,
    PlannedInsert,
    PredecessorRow,
    TemporalObservation,
    VersionObservation,
    WritePlanningError,
)
from parallax.core.write_plan.keys import TemporalStateKey
from parallax.core.write_plan.plan import CombinedSourceAuthority, WritePlan
from tests._support.clock_probes import instant_at
from tests._support.planner_probes import TEST_ACTOR_IDENTITY
from tests.unit._corpus_model_support import corpus_records, formed

_BALANCE = formed(corpus_records()["balance"])
_ENTITY = EntityIdentity("parallax.compatibility", "Balance")
_OBJECT = ObjectKey(_ENTITY, (("id", 1),))
_JAN = dt.datetime(2024, 1, 1, tzinfo=dt.UTC)
_MAR = dt.datetime(2024, 3, 1, tzinfo=dt.UTC)


def _observation(tx_start: dt.datetime, value: str) -> RetainedObservation:
    """A retained observation of Balance 1's milestone opened at ``tx_start``."""
    observation = TemporalObservation(
        predecessor=PredecessorRow(
            members={
                "id": 1,
                "acctNum": "A",
                "value": Decimal(value),
                "txStart": tx_start,
                "txEnd": INFINITY,
            }
        )
    )
    shape = temporal_read.view(_BALANCE).shape(_ENTITY)
    assert shape is not None
    state = TemporalStateKey(
        _OBJECT, temporal_read.milestone_edge(shape, observation.predecessor, None)
    )
    return RetainedObservation(state, observation, None)


_STALE = _observation(_JAN, "100.00")
_CURRENT = _observation(_MAR, "120.00")


def _write(
    mutation: KeyedMutation, evidence: RetainedObservation, **members: object
) -> ObservedKeyedWrite:
    prepared = prepare_wire_write(
        KeyedWrite(mutation, "Balance", ({"id": 1, **members},)), _BALANCE
    )
    item = buffered_write(prepared, evidence)
    assert isinstance(item, ObservedKeyedWrite)
    return item


def _plan(*writes: ObservedKeyedWrite) -> WritePlan:
    return build_write_planner(_BALANCE).finalize(
        WritePlanningRequest(
            actor_identity=TEST_ACTOR_IDENTITY,
            transaction_instant=instant_at("2024-06-01T00:00:00+00:00"),
            concurrency="optimistic",
            buffered_writes=compose_writes(_BALANCE, writes),
        )
    )


def test_two_observations_of_one_transaction_time_row_validate_the_earlier() -> None:
    # Two observations of one Transaction-Time-Only row cannot both be current:
    # the later-authored one is the milestone the composition rewrites, and the
    # earlier is closed on its own gated address first, so a stale condition
    # fails before anything opens. Both sources are spent by the one unit.
    plan = _plan(_write("amend", _STALE, value="150.00"), _write("amend", _CURRENT, value="175.00"))
    steps = list(plan.steps)
    assert [type(step) for step in steps] == [PlannedClose, PlannedClose, PlannedInsert]
    assert [step.cause for step in steps if isinstance(step, PlannedClose)] == [
        TERMINATED,
        SUPERSEDED,
    ]
    successor = steps[2]
    assert isinstance(successor, PlannedInsert)
    (entry,) = successor.entries
    assert {ident.name: value for ident, value in entry.row.attributes.items()}["value"] == (
        Decimal("175.00")
    )
    (unit,) = plan.units
    assert isinstance(unit.claim, CombinedSourceAuthority)
    unit.claim.consume()
    assert _STALE.consumed and _CURRENT.consumed


def test_terminations_through_two_observations_compose_to_destruction_alone() -> None:
    # A composition that assigns nothing destroys the row it reaches and opens
    # nothing, ordered as a destructive write.
    stale, current = _observation(_JAN, "100.00"), _observation(_MAR, "120.00")
    composed = compose_writes(_BALANCE, [_write("terminate", stale), _write("terminate", current)])
    (write,) = composed
    assert isinstance(write, ComposedTemporalWrite) and not write.assigns
    steps = list(_plan(_write("terminate", stale), _write("terminate", current)).steps)
    assert [type(step) for step in steps] == [PlannedClose, PlannedClose]


def test_a_termination_after_an_update_through_another_observation_ends_the_row() -> None:
    stale, current = _observation(_JAN, "100.00"), _observation(_MAR, "120.00")
    steps = list(
        _plan(
            _write("amend", stale, value="150.00"),
            _write("terminate", current),
            _write("terminate", current),
        ).steps
    )
    assert [type(step) for step in steps] == [PlannedClose, PlannedClose]


def test_a_repeated_termination_of_one_observation_adds_nothing() -> None:
    current = _observation(_MAR, "120.00")
    (write,) = compose_writes(
        _BALANCE, [_write("terminate", current), _write("terminate", current)]
    )
    assert isinstance(write, ObservedKeyedWrite)


def test_a_pair_no_verb_admitted_is_left_standing_rather_than_composed() -> None:
    # An assignment after a destruction over the same coverage resurrects
    # nothing; a buffer no unit of work admitted keeps both writes as authored.
    stale, current = _observation(_JAN, "100.00"), _observation(_MAR, "120.00")
    composed = compose_writes(
        _BALANCE, [_write("terminate", stale), _write("amend", current, value="1.00")]
    )
    assert [type(write) for write in composed] == [ObservedKeyedWrite, ObservedKeyedWrite]


def test_completions_spend_every_member() -> None:
    first, second = _observation(_JAN, "1.00"), _observation(_MAR, "2.00")
    CombinedSourceAuthority((first, second)).consume()
    assert first.consumed and second.consumed


def test_a_bitemporal_write_carrying_no_temporal_observation_is_refused_as_unobserved() -> None:
    # Only a Temporal Observation states a predecessor a range could start
    # from, so any other evidence reaches the ordinary required-observation
    # refusal rather than a range.
    model = formed(corpus_records()["position"])
    prepared = prepare_wire_write(
        KeyedWrite(
            "amend",
            "Position",
            ({"id": 1, "value": "1.00"},),
            dt.datetime(2024, 3, 1, tzinfo=dt.UTC),
        ),
        model,
    )
    with pytest.raises(WritePlanningError, match="requires the Temporal Observation"):
        build_write_planner(model).finalize(
            WritePlanningRequest(
                actor_identity=TEST_ACTOR_IDENTITY,
                transaction_instant=instant_at("2024-06-01T00:00:00+00:00"),
                concurrency="optimistic",
                buffered_writes=compose_writes(
                    model, [buffered_write(prepared, VersionObservation(observed_version=1))]
                ),
            )
        )


def test_two_observed_rectangles_bind_at_planning_when_they_cover_the_range() -> None:
    # Two reads of one object observed two disjoint rectangles that together
    # cover everything both writes request, so the composition binds at
    # planning: each rectangle closes once, then every piece opens.
    model = formed(corpus_records()["position"])
    jun, aug = dt.datetime(2024, 6, 1, tzinfo=dt.UTC), dt.datetime(2024, 8, 1, tzinfo=dt.UTC)

    def rectangle(start: dt.datetime, end: object, value: str) -> TemporalObservation:
        return TemporalObservation(
            predecessor=PredecessorRow(
                members={
                    "id": 1,
                    "acctNum": "A",
                    "value": Decimal(value),
                    "validStart": start,
                    "validEnd": end,
                    "txStart": _JAN,
                    "txEnd": INFINITY,
                }
            )
        )

    def update(valid_from: dt.datetime, value: str, observed: TemporalObservation) -> BufferItem:
        prepared = prepare_wire_write(
            KeyedWrite("amend", "Position", ({"id": 1, "value": value},), valid_from), model
        )
        return buffered_write(prepared, observed)

    writes = compose_writes(
        model,
        [
            update(_MAR, "150.00", rectangle(_JAN, jun, "100.00")),
            update(aug, "300.00", rectangle(jun, INFINITY, "200.00")),
        ],
    )
    plan = build_write_planner(model).finalize(
        WritePlanningRequest(
            actor_identity=TEST_ACTOR_IDENTITY,
            transaction_instant=instant_at("2024-10-01T00:00:00+00:00"),
            concurrency="optimistic",
            buffered_writes=writes,
        )
    )
    assert [type(step) for step in plan.steps] == [PlannedClose] * 2 + [PlannedInsert] * 4
    (unit,) = plan.units
    assert unit.deferred is None
