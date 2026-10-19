"""``parallax.conformance.simulated_temporal_store.SimulatedTemporalStore`` unit tests.

The case-local stored rows that supply the engine's write lanes with an
observed current milestone are proven end to end through the engine's own
writeSequence/scenario tests (``test_engine.py``, ``test_compile_sweep.py``,
``test_run_sweep.py``); this module pins the store's OWN seam directly —
fixture seeding, resolution, addressing a row by its complete address, applying
planned steps to the rows, the row acquisition it answers, and the transaction
that restores them — including the disambiguation refusals no reachable corpus
case witnesses.
"""

from __future__ import annotations

import contextlib
import datetime as dt
import decimal
from collections.abc import Callable, Generator, Iterator, Mapping, Sequence
from typing import Final, cast

import pytest

from parallax.conformance import _case_ingress, models
from parallax.conformance.scripted_clock import FixedClock
from parallax.conformance.simulated_temporal_store import (
    AmbiguousObservationError,
    MilestoneEdgeError,
    SimulatedStoreError,
    SimulatedTemporalStore,
)
from parallax.core import temporal_read
from parallax.core._execution._planning import build_write_planner
from parallax.core._execution._unit_work import instructions
from parallax.core._execution._unit_work.acquisition import (
    CompletionRequest,
    CoverageReadRequest,
    CoverageTerm,
    RowRequest,
    TargetReadRequest,
)
from parallax.core._execution._unit_work.instructions import KeyedWrite, PreparedKeyedWrite
from parallax.core._execution._unit_work.write_items import ObservedKeyedWrite
from parallax.core.base import INFINITY
from parallax.core.inheritance import EntityMemberSelection
from parallax.core.metamodel import (
    AttributeIdentity,
    EntityIdentity,
    EntityMetadata,
    Metamodel,
    ValueObjectIdentity,
)
from parallax.core.temporal_read import TimeInterval
from parallax.core.unit_work import (
    RetainedObservation,
    SubjectActor,
    TransactionInstant,
    WritePlanningRequest,
)
from parallax.core.write_plan import (
    ObjectKey,
    PredecessorRow,
    TemporalObservation,
    object_state_key_from_observation,
)
from parallax.core.write_plan.plan import PlannedWrites
from parallax.core.write_plan.steps import INFINITY as OPEN_END
from parallax.core.write_plan.steps import (
    MAX_PLUS_ONE,
    MISSING_TARGET,
    NEW_LINEAGE,
    OPTIMISTIC_CONFLICT,
    STALE_WRITE,
    SUPERSEDED,
    UNGATED,
    UNVERSIONED,
    ExactCount,
    Finite,
    KeyTarget,
    MilestoneTarget,
    PlannedAssignments,
    PlannedClose,
    PlannedDelete,
    PlannedInsert,
    PlannedRow,
    PlannedTemporalGuard,
    PlannedTemporalRemoval,
    PlannedTemporalRevision,
    PlannedUpdate,
    TemporalGate,
    Versioned,
    WriteRow,
)
from tests.unit.conformance._coverage_rows_support import coverage_members, read_coverage

POSITION = models.load_models()["position"]
_POSITION_ENTITY = POSITION.entity(EntityIdentity("parallax.compatibility", "Position"))
assert _POSITION_ENTITY is not None
POSITION_ENTITY = _POSITION_ENTITY

BALANCE = models.load_models()["balance"]
_BALANCE_ENTITY = BALANCE.entity(EntityIdentity("parallax.compatibility", "Balance"))
assert _BALANCE_ENTITY is not None
BALANCE_ENTITY = _BALANCE_ENTITY

# The two rectangles of one key that are current on Transaction Time at once
# (the `position` fixtures' pair): identical primary key, identical open
# Transaction-Time bound, identical `txStart`. Only their edges tell them apart.
_HEAD = {
    "id": 1,
    "acctNum": "A",
    "value": 100.00,
    "validStart": dt.datetime(2024, 1, 1, tzinfo=dt.UTC),
    "validEnd": dt.datetime(2024, 6, 1, tzinfo=dt.UTC),
    "txStart": dt.datetime(2024, 4, 1, tzinfo=dt.UTC),
    "txEnd": INFINITY,
}
_TAIL = {
    "id": 1,
    "acctNum": "A",
    "value": 200.00,
    "validStart": dt.datetime(2024, 6, 1, tzinfo=dt.UTC),
    "validEnd": INFINITY,
    "txStart": dt.datetime(2024, 4, 1, tzinfo=dt.UTC),
    "txEnd": INFINITY,
}


def test_predecessor_for_refuses_a_pk_with_more_than_one_current_milestone() -> None:
    # Two rectangles for the SAME pk share an in_z (both current on Transaction
    # Time, different Valid Time windows) — the store refuses to guess which one
    # a later un-discriminated write means; a write that must address one of them
    # names the find it settles against instead
    # (`SimulatedTemporalStore.predecessor_for`'s own docstring).
    store = SimulatedTemporalStore()
    store.seed_fixtures(
        POSITION,
        POSITION_ENTITY,
        [
            {
                "id": 1,
                "acctNum": "A",
                "value": 100.00,
                "validStart": dt.datetime(2024, 1, 1, tzinfo=dt.UTC),
                "validEnd": dt.datetime(2024, 6, 1, tzinfo=dt.UTC),
                "txStart": dt.datetime(2024, 1, 1, tzinfo=dt.UTC),
                "txEnd": INFINITY,
            },
            {
                "id": 1,
                "acctNum": "A",
                "value": 200.00,
                "validStart": dt.datetime(2024, 6, 1, tzinfo=dt.UTC),
                "validEnd": INFINITY,
                "txStart": dt.datetime(2024, 1, 1, tzinfo=dt.UTC),
                "txEnd": INFINITY,
            },
        ],
    )
    with pytest.raises(AmbiguousObservationError, match="2 current milestones"):
        store.predecessor_for(POSITION, POSITION_ENTITY, {"id": 1})


def test_predecessor_for_returns_none_for_a_pk_the_tracker_has_never_seen_open() -> None:
    # An insert's pk, or a genuinely unobserved close: the write itself
    # surfaces a conflict/stale error at execution, never this tracker.
    store = SimulatedTemporalStore()
    assert store.predecessor_for(POSITION, POSITION_ENTITY, {"id": 99}) is None


def test_seed_fixtures_skips_a_row_not_current_on_transaction_time() -> None:
    # A historical (superseded) row — out_z finite — is never a later write's
    # observed row.
    store = SimulatedTemporalStore()
    store.seed_fixtures(
        POSITION,
        POSITION_ENTITY,
        [
            {
                "id": 1,
                "acctNum": "A",
                "value": 100.00,
                "validStart": dt.datetime(2024, 1, 1, tzinfo=dt.UTC),
                "validEnd": INFINITY,
                "txStart": dt.datetime(2024, 1, 1, tzinfo=dt.UTC),
                "txEnd": dt.datetime(2024, 6, 1, tzinfo=dt.UTC),
            }
        ],
    )
    assert store.predecessor_for(POSITION, POSITION_ENTITY, {"id": 1}) is None


@pytest.mark.parametrize(
    "valid_start", [INFINITY, "infinity", "2024-01-01T00:00:00+00:00", 20240101]
)
def test_an_axis_start_that_is_not_a_finite_instant_is_refused(valid_start: object) -> None:
    # A milestone's edge is its from-instant per axis. The open bound belongs to
    # an axis END, and neither a bare number nor an unmanaged instant spelling is
    # a managed coordinate — each would key a slot no read can ever match, so all
    # are refused where the slot is keyed.
    with pytest.raises(MilestoneEdgeError, match="finite instant"):
        SimulatedTemporalStore().seed_fixtures(
            POSITION, POSITION_ENTITY, [{**_HEAD, "validStart": valid_start}]
        )


def _planned(
    entity_name: str, members: dict[str, object], *, valid_from: str, at: str
) -> PlannedWrites:
    """The Write Plan an insert of ``members`` produces, through the SAME
    ``build_write_planner`` factory the engine's own write lanes plan with — so
    what the store holds is what a flush would actually write."""
    instruction = instructions.deserialize(
        {"mutation": "insert", "entity": entity_name, "rows": [members], "validFrom": valid_from}
    )
    assert isinstance(instruction, KeyedWrite)  # a `rows` document is a keyed write
    prepared = instructions.prepare_wire_write(instruction, POSITION)
    return (
        build_write_planner(POSITION)
        .finalize(
            WritePlanningRequest(
                actor_identity=SubjectActor("unattributed"),
                transaction_instant=TransactionInstant(FixedClock(dt.datetime.fromisoformat(at))),
                concurrency="locking",
                buffered_writes=[prepared],
            )
        )
        .steps
    )


def _apply_all(store: SimulatedTemporalStore, model: Metamodel, steps: PlannedWrites) -> None:
    for step in steps:
        store.apply(model, step)


def _observed_write(
    prepared: PreparedKeyedWrite, observation: TemporalObservation
) -> ObservedKeyedWrite:
    shape = temporal_read.view(POSITION).shape(POSITION_ENTITY.identity)
    assert shape is not None
    key = ObjectKey(POSITION_ENTITY.identity, (("id", 1),))
    retained = RetainedObservation(
        object_state_key_from_observation(key, observation, shape), observation, None
    )
    return ObservedKeyedWrite(prepared, retained)


@pytest.mark.parametrize(
    ("value", "kept"), [("100.00", True), ("150.00", False)], ids=["kept", "closed"]
)
def test_a_milestone_no_planned_step_closes_stays_stored_as_it_was(value: str, kept: bool) -> None:
    # A write leaving a milestone as it was keeps it current (`m-temporal-write`):
    # its plan guards the row rather than closing it, and a guard changes nothing.
    store = SimulatedTemporalStore()
    store.seed_fixtures(POSITION, POSITION_ENTITY, [_HEAD])
    observed = store.predecessor_for(POSITION, POSITION_ENTITY, {"id": 1})
    assert observed is not None
    prepared = instructions.prepare_wire_write(
        KeyedWrite(
            "amendUntil",
            "Position",
            ({"id": 1, "value": value},),
            dt.datetime(2024, 2, 1, tzinfo=dt.UTC),
            dt.datetime(2024, 3, 1, tzinfo=dt.UTC),
        ),
        POSITION,
    )
    steps = (
        build_write_planner(POSITION)
        .finalize(
            WritePlanningRequest(
                actor_identity=SubjectActor("unattributed"),
                transaction_instant=TransactionInstant(
                    FixedClock(dt.datetime(2024, 9, 1, tzinfo=dt.UTC))
                ),
                concurrency="locking",
                buffered_writes=[_observed_write(prepared, observed)],
            )
        )
        .steps
    )
    for step in steps:
        store.apply(POSITION, step)
    assert (_stored(store) == [_HEAD_ROW]) is kept
    if kept:
        assert store.predecessor_for(POSITION, POSITION_ENTITY, {"id": 1}) is observed


def test_an_applied_insert_stores_the_milestone_its_plan_opens() -> None:
    # The store advances by the plan the write lane already produced, so a
    # plain insert's one opened rectangle is stored with the framework-owned
    # interval bounds the plan stamped on it — never a second expansion of the
    # same topology computed beside it.
    store = SimulatedTemporalStore()
    _apply_all(
        store,
        POSITION,
        _planned(
            "Position",
            {"id": 1, "acctNum": "A", "value": "100.00"},
            valid_from="2024-01-01T00:00:00Z",
            at="2024-01-01T00:00:00+00:00",
        ),
    )
    observation = store.predecessor_for(POSITION, POSITION_ENTITY, {"id": 1})
    assert observation is not None
    assert dict(observation.predecessor.members) == {
        "id": 1,
        "acctNum": "A",
        "value": decimal.Decimal("100.00"),
        "validStart": dt.datetime(2024, 1, 1, tzinfo=dt.UTC),
        "validEnd": INFINITY,
        "txStart": dt.datetime(2024, 1, 1, tzinfo=dt.UTC),
        "txEnd": INFINITY,
    }


def test_an_applied_non_temporal_insert_stores_nothing() -> None:
    # A non-temporal insert opens no milestone, so a stored row for it would
    # answer no question a later step can ask.
    store = SimulatedTemporalStore()
    instruction = instructions.deserialize(
        {
            "mutation": "insert",
            "entity": "Account",
            "rows": [{"id": 1, "owner": "Ada", "balance": "0.00"}],
        }
    )
    assert isinstance(instruction, KeyedWrite)  # a `rows` document is a keyed write
    account = models.load_models()["account"]
    prepared = instructions.prepare_wire_write(instruction, account)
    plan = build_write_planner(account).finalize(
        WritePlanningRequest(
            actor_identity=SubjectActor("unattributed"),
            transaction_instant=TransactionInstant(
                FixedClock(dt.datetime(2024, 1, 1, tzinfo=dt.UTC))
            ),
            concurrency="locking",
            buffered_writes=[prepared],
        )
    )
    _apply_all(store, account, plan.steps)
    entity = account.entity(EntityIdentity("parallax.compatibility", "Account"))
    assert entity is not None
    assert store.predecessor_for(account, entity, {"id": 1}) is None


def test_two_tracked_milestones_of_one_key_sharing_an_edge_are_refused() -> None:
    # An edge names exactly one milestone, so a state holding two current
    # milestones of one key at one edge is unaddressable: keeping the later would
    # hand every subsequent step a row no case selected.
    store = SimulatedTemporalStore()
    twin = {**_TAIL, "value": 300.00, "validStart": _HEAD["validStart"]}
    with pytest.raises(AmbiguousObservationError, match="carry the edge"):
        store.seed_fixtures(POSITION, POSITION_ENTITY, [_HEAD, twin])


def _rectangles(
    *spans: tuple[int, str, str | None, str],
) -> PlannedWrites:
    """The plan opening one rectangle per ``(id, validFrom, until, value)``."""
    entries: list[PreparedKeyedWrite] = []
    for key, valid_from, until, value in spans:
        document: dict[str, object] = {
            "mutation": "insert" if until is None else "insertUntil",
            "entity": "Position",
            "rows": [{"id": key, "acctNum": "A", "value": value}],
            "validFrom": valid_from,
        }
        if until is not None:
            document["until"] = until
        instruction = instructions.deserialize(document)
        assert isinstance(instruction, KeyedWrite)  # a `rows` document is a keyed write
        entries.append(instructions.prepare_wire_write(instruction, POSITION))
    return (
        build_write_planner(POSITION)
        .finalize(
            WritePlanningRequest(
                actor_identity=SubjectActor("unattributed"),
                transaction_instant=TransactionInstant(
                    FixedClock(dt.datetime(2024, 1, 1, tzinfo=dt.UTC))
                ),
                concurrency="locking",
                buffered_writes=entries,
            )
        )
        .steps
    )


def _acquisition(valid_from: dt.datetime, until: dt.datetime | None) -> CoverageReadRequest:
    key = AttributeIdentity(POSITION_ENTITY.identity, "id")
    return CoverageReadRequest(
        entity=POSITION_ENTITY,
        key_attribute=key,
        terms=(CoverageTerm(1, (TimeInterval(valid_from, INFINITY if until is None else until),)),),
        locking=False,
    )


def test_coverage_answers_the_stored_rectangles_of_one_object_inside_the_window() -> None:
    store = SimulatedTemporalStore()
    _apply_all(
        store,
        POSITION,
        _rectangles(
            (1, "2024-01-01T00:00:00Z", "2024-03-01T00:00:00Z", "1.00"),
            (1, "2024-03-01T00:00:00Z", "2024-06-01T00:00:00Z", "2.00"),
            (1, "2024-06-01T00:00:00Z", None, "3.00"),
            (2, "2024-01-01T00:00:00Z", None, "9.00"),
        ),
    )
    covered = read_coverage(
        store,
        POSITION,
        _acquisition(
            dt.datetime(2024, 4, 1, tzinfo=dt.UTC), dt.datetime(2024, 6, 1, tzinfo=dt.UTC)
        ),
    )
    assert [row["value"] for row in coverage_members(covered)] == [decimal.Decimal("2.00")]


def test_coverage_reaches_a_stored_opening_whose_end_is_the_open_bound() -> None:
    store = SimulatedTemporalStore()
    _apply_all(
        store,
        POSITION,
        _rectangles(
            (1, "2024-01-01T00:00:00Z", "2024-03-01T00:00:00Z", "1.00"),
            (1, "2024-03-01T00:00:00Z", None, "2.00"),
        ),
    )
    covered = read_coverage(
        store, POSITION, _acquisition(dt.datetime(2024, 4, 1, tzinfo=dt.UTC), None)
    )
    assert [(row["value"], row["validEnd"]) for row in coverage_members(covered)] == [
        (decimal.Decimal("2.00"), INFINITY)
    ]


def test_coverage_reaches_a_fixture_row_decoded_at_case_ingress() -> None:
    # A fixture states its open ends as the published literal; case ingress
    # decodes the declared axis ends to the managed bound before seeding, so
    # the seeded milestone is current and covers every window it reaches.
    fixture = {
        "id": 1,
        "acctNum": "A",
        "value": "100.00",
        "validStart": "2024-01-01T00:00:00.000000Z",
        "validEnd": "infinity",
        "txStart": "2024-01-01T00:00:00.000000Z",
        "txEnd": "infinity",
    }
    store = SimulatedTemporalStore()
    store.seed_fixtures(
        POSITION,
        POSITION_ENTITY,
        [_case_ingress.decode_case_row(fixture, POSITION, POSITION_ENTITY)],
    )
    covered = read_coverage(
        store,
        POSITION,
        _acquisition(
            dt.datetime(2024, 9, 1, tzinfo=dt.UTC), dt.datetime(2024, 10, 1, tzinfo=dt.UTC)
        ),
    )
    assert [(row["validEnd"], row["txEnd"]) for row in coverage_members(covered)] == [
        (INFINITY, INFINITY)
    ]


def test_coverage_answers_a_stored_milestones_value_objects_positionally() -> None:
    model = models.load_models()["document-layout"]
    entity = model.entity(EntityIdentity("parallax.compatibility", "Voyage"))
    assert entity is not None
    members: dict[str, object] = {
        "id": 7,
        "title": "Northbound",
        "crew": 12,
        "manifest": {"cargo": "grain"},
        "legs": [{"port": "Oslo"}, {"port": "Bergen"}],
        "txStart": dt.datetime(2024, 1, 1, tzinfo=dt.UTC),
        "txEnd": INFINITY,
    }
    store = SimulatedTemporalStore()
    store.seed_fixtures(model, entity, [members])
    covered = read_coverage(
        store,
        model,
        CoverageReadRequest(
            entity=entity,
            key_attribute=AttributeIdentity(entity.identity, "id"),
            terms=(CoverageTerm(7, ()),),
            locking=False,
        ),
    )
    (row,) = coverage_members(covered)
    assert dict(cast("Mapping[str, object]", row["manifest"])) == {"cargo": "grain"}
    legs = cast("tuple[Mapping[str, object], ...]", row["legs"])
    assert [dict(leg) for leg in legs] == [{"port": "Oslo"}, {"port": "Bergen"}]
    assert (row["title"], row["txEnd"]) == ("Northbound", INFINITY)


def test_coverage_of_an_object_it_tracks_no_milestone_of_is_no_evidence() -> None:
    assert (
        read_coverage(
            SimulatedTemporalStore(),
            POSITION,
            _acquisition(dt.datetime(2024, 1, 1, tzinfo=dt.UTC), None),
        )
        is None
    )


# --------------------------------------------------------------------------- #
# A planned step changes the row its complete address names.                 #
# --------------------------------------------------------------------------- #
_JAN, _MAR, _JUN, _SEP = (dt.datetime(2024, month, 1, tzinfo=dt.UTC) for month in (1, 3, 6, 9))
_NOW = dt.datetime(2024, 9, 1, tzinfo=dt.UTC)


def _position(name: str) -> AttributeIdentity:
    return AttributeIdentity(POSITION_ENTITY.identity, name)


def _addressing(valid_end: dt.datetime | None, key: int = 1) -> MilestoneTarget:
    return MilestoneTarget(
        key_attributes=(_position("id"),),
        key_values=(key,),
        end_attributes=(_position("validEnd"), _position("txEnd")),
        end_values=(OPEN_END if valid_end is None else Finite(valid_end), OPEN_END),
    )


def _close(valid_end: dt.datetime | None, key: int = 1) -> PlannedClose:
    return PlannedClose(
        entity=POSITION_ENTITY.identity,
        target=_addressing(valid_end, key),
        assignments=PlannedAssignments(attributes={_position("txEnd"): _NOW}),
        cause=SUPERSEDED,
        concurrency=UNGATED,
        affected_rows=ExactCount(1, STALE_WRITE),
    )


def _revision(valid_end: dt.datetime | None, **assigned: object) -> PlannedTemporalRevision:
    return PlannedTemporalRevision(
        entity=POSITION_ENTITY.identity,
        target=_addressing(valid_end),
        assignments=PlannedAssignments(
            attributes={_position(name): value for name, value in assigned.items()}
        ),
        concurrency=UNGATED,
        affected_rows=ExactCount(1, STALE_WRITE),
    )


def _opening(key: int, start: dt.datetime, end: object, value: str) -> PlannedInsert:
    members: dict[str, object] = {
        "id": key,
        "acctNum": "A",
        "value": decimal.Decimal(value),
        "validStart": start,
        "validEnd": end,
        "txStart": _NOW,
        "txEnd": INFINITY,
    }
    row = PlannedRow(attributes={_position(name): value for name, value in members.items()})
    return PlannedInsert(entity=POSITION_ENTITY.identity, entries=(WriteRow(row, NEW_LINEAGE),))


def _stored(store: SimulatedTemporalStore, key: int = 1) -> list[tuple[object, object, object]]:
    """Every row ``store`` holds current for Position ``key``, as
    ``(validStart, validEnd, value)``, by Valid-Time start."""
    covered = read_coverage(
        store,
        POSITION,
        CoverageReadRequest(
            entity=POSITION_ENTITY,
            key_attribute=_position("id"),
            terms=(CoverageTerm(key, ()),),
            locking=False,
        ),
    )
    return sorted(
        ((row["validStart"], row["validEnd"], row["value"]) for row in coverage_members(covered)),
        key=lambda stored: cast("dt.datetime", stored[0]),
    )


_HEAD_ROW = (_HEAD["validStart"], _HEAD["validEnd"], _HEAD["value"])
_TAIL_ROW = (_TAIL["validStart"], _TAIL["validEnd"], _TAIL["value"])


@pytest.mark.parametrize(
    ("valid_end", "left"),
    [(_JUN, [_TAIL_ROW]), (None, [_HEAD_ROW])],
    ids=["bounded", "open"],
)
def test_a_close_retires_only_the_sibling_rectangle_its_address_names(
    valid_end: dt.datetime | None, left: list[tuple[object, object, object]]
) -> None:
    store = SimulatedTemporalStore()
    store.seed_fixtures(POSITION, POSITION_ENTITY, [_HEAD, _TAIL])
    store.apply(POSITION, _close(valid_end))
    assert _stored(store) == left


def test_a_removal_retires_its_row_and_a_guard_or_non_temporal_step_changes_nothing() -> None:
    store = SimulatedTemporalStore()
    store.seed_fixtures(POSITION, POSITION_ENTITY, [_HEAD, _TAIL])
    store.apply(
        POSITION,
        PlannedTemporalGuard(
            entity=POSITION_ENTITY.identity,
            target=_addressing(_JUN),
            concurrency=TemporalGate(_position("txStart"), _HEAD["txStart"]),
            affected_rows=ExactCount(1, OPTIMISTIC_CONFLICT),
        ),
    )
    store.apply(
        POSITION,
        PlannedDelete(
            entity=BALANCE_ENTITY.identity,
            target=KeyTarget((AttributeIdentity(BALANCE_ENTITY.identity, "id"),), ((1,),)),
            concurrency=UNVERSIONED,
            affected_rows=ExactCount(1, MISSING_TARGET),
        ),
    )
    assert _stored(store) == [_HEAD_ROW, _TAIL_ROW]
    store.apply(
        POSITION,
        PlannedTemporalRemoval(
            entity=POSITION_ENTITY.identity,
            target=_addressing(None),
            concurrency=UNGATED,
            affected_rows=ExactCount(1, STALE_WRITE),
        ),
    )
    assert _stored(store) == [_HEAD_ROW]


def test_a_target_no_stored_row_answers_changes_nothing() -> None:
    store = SimulatedTemporalStore()
    store.seed_fixtures(POSITION, POSITION_ENTITY, [_HEAD])
    store.apply(POSITION, _close(None))
    store.apply(POSITION, _revision(_SEP, value=decimal.Decimal("1.00")))
    assert _stored(store) == [_HEAD_ROW]


def test_every_row_an_insert_opens_is_addressable_where_a_retired_one_was() -> None:
    store = SimulatedTemporalStore()
    store.seed_fixtures(POSITION, POSITION_ENTITY, [_HEAD, _TAIL])
    store.apply(POSITION, _close(None))
    store.apply(POSITION, _opening(1, _JUN, INFINITY, "250.00"))
    store.apply(POSITION, _opening(2, _JAN, _MAR, "9.00"))
    assert _stored(store) == [_HEAD_ROW, (_JUN, INFINITY, decimal.Decimal("250.00"))]
    store.apply(POSITION, _close(None))
    store.apply(POSITION, _close(_MAR, key=2))
    assert (_stored(store), _stored(store, 2)) == ([_HEAD_ROW], [])


def test_a_revision_replaces_what_it_assigns_and_leaves_earlier_evidence_as_it_was() -> None:
    store = SimulatedTemporalStore()
    store.seed_fixtures(POSITION, POSITION_ENTITY, [_HEAD])
    before = store.predecessor_for(POSITION, POSITION_ENTITY, {"id": 1})
    assert before is not None
    store.apply(POSITION, _revision(_JUN, value=decimal.Decimal("150.00")))
    after = store.predecessor_for(POSITION, POSITION_ENTITY, {"id": 1})
    assert after is not None
    assert dict(after.predecessor.members) == {**_HEAD, "value": decimal.Decimal("150.00")}
    assert dict(before.predecessor.members) == _HEAD


def test_a_revision_moving_its_valid_time_start_moves_the_row_to_its_new_edge() -> None:
    store = SimulatedTemporalStore()
    store.seed_fixtures(POSITION, POSITION_ENTITY, [_HEAD])
    store.apply(POSITION, _revision(_JUN, validStart=_MAR))
    assert _stored(store) == [(_MAR, _JUN, _HEAD["value"])]
    # The row no longer reaches the Valid Time it left, and its address is
    # unchanged.
    assert read_coverage(store, POSITION, _acquisition(_JAN, _MAR)) is None
    # A row may now take the edge the revision left.
    store.seed_fixtures(POSITION, POSITION_ENTITY, [{**_HEAD, "validEnd": _MAR}])
    store.apply(POSITION, _close(_JUN))
    assert _stored(store) == [(_JAN, _MAR, _HEAD["value"])]


def test_a_value_object_assignment_replaces_the_stored_occurrence_whole() -> None:
    model = models.load_models()["document-layout"]
    entity = model.entity(EntityIdentity("parallax.compatibility", "Voyage"))
    assert entity is not None
    members: dict[str, object] = {
        "id": 7,
        "title": "Northbound",
        "crew": 12,
        "manifest": {"cargo": "grain"},
        "legs": [{"port": "Oslo"}, {"port": "Bergen"}],
        "txStart": _JAN,
        "txEnd": INFINITY,
    }
    store = SimulatedTemporalStore()
    store.seed_fixtures(model, entity, [members])
    store.apply(
        model,
        PlannedTemporalRevision(
            entity=entity.identity,
            target=MilestoneTarget(
                key_attributes=(AttributeIdentity(entity.identity, "id"),),
                key_values=(7,),
                end_attributes=(AttributeIdentity(entity.identity, "txEnd"),),
                end_values=(OPEN_END,),
            ),
            assignments=PlannedAssignments(
                attributes={},
                value_objects={
                    ValueObjectIdentity(entity.identity, ("legs",)): ({"port": "Tromsø"},)
                },
            ),
            concurrency=UNGATED,
            affected_rows=ExactCount(1, STALE_WRITE),
        ),
    )
    revised = store.predecessor_for(model, entity, {"id": 7})
    assert revised is not None
    assert [
        dict(leg)
        for leg in cast("tuple[Mapping[str, object], ...]", revised.predecessor.member("legs"))
    ] == [{"port": "Tromsø"}]
    assert dict(cast("Mapping[str, object]", revised.predecessor.member("manifest"))) == {
        "cargo": "grain"
    }
    assert revised.predecessor.member("title") == "Northbound"


def test_a_revision_re_accounts_for_nothing_the_store_had_lost_track_of() -> None:
    store = SimulatedTemporalStore()
    store.seed_fixtures(POSITION, POSITION_ENTITY, [_HEAD])
    store.note_out_of_band_write()
    store.note_materialized_write(POSITION_ENTITY)
    store.apply(POSITION, _revision(_JUN, validStart=_MAR))
    assert not store.has_complete_stored_row(POSITION, POSITION_ENTITY, {"id": 1})
    assert store.moved_by_materialization(POSITION, POSITION_ENTITY, {"id": 1})


def test_storing_a_row_again_as_it_is_keeps_one_addressable_row() -> None:
    store = SimulatedTemporalStore()
    store.seed_fixtures(POSITION, POSITION_ENTITY, [_HEAD])
    store.seed_fixtures(POSITION, POSITION_ENTITY, [_HEAD])
    store.apply(POSITION, _close(_JUN))
    assert _stored(store) == []


def test_rows_sharing_one_complete_address_are_refused_rather_than_guessed() -> None:
    # Distinct edges, so both are stored; one key and one set of axis ends, so
    # no planned step could name either of them alone.
    store = SimulatedTemporalStore()
    later = {**_TAIL, "validStart": _SEP}
    store.seed_fixtures(POSITION, POSITION_ENTITY, [_TAIL, later])
    with pytest.raises(AmbiguousObservationError, match="share both"):
        store.apply(POSITION, _close(None))
    assert _stored(store) == [_TAIL_ROW, (_SEP, INFINITY, _TAIL["value"])]


def test_an_axis_end_neither_finite_nor_open_is_refused() -> None:
    with pytest.raises(MilestoneEdgeError, match="axis end"):
        SimulatedTemporalStore().seed_fixtures(
            POSITION, POSITION_ENTITY, [{**_HEAD, "validEnd": "2024-06-01"}]
        )


# --------------------------------------------------------------------------- #
# A simulated transaction keeps its changes only if it commits.               #
# --------------------------------------------------------------------------- #
class _Failed(Exception):
    pass


def test_a_committed_transaction_keeps_what_ran_inside_it() -> None:
    store = SimulatedTemporalStore()
    store.seed_fixtures(POSITION, POSITION_ENTITY, [_HEAD, _TAIL])
    with store.transaction(rollback=False):
        store.apply(POSITION, _close(None))
    assert _stored(store) == [_HEAD_ROW]
    store.apply(POSITION, _close(_JUN))
    assert _stored(store) == []


def test_a_restarted_transaction_begins_again_from_what_it_began_with() -> None:
    store = SimulatedTemporalStore()
    store.seed_fixtures(POSITION, POSITION_ENTITY, [_HEAD, _TAIL])
    with store.transaction(rollback=False) as restart:
        for _attempt in range(2):
            restart()
            store.apply(POSITION, _close(None))
            store.note_out_of_band_write()
            assert _stored(store) == [_HEAD_ROW]
        restart()
    assert _stored(store) == [_HEAD_ROW, _TAIL_ROW]
    assert store.has_complete_stored_row(POSITION, POSITION_ENTITY, {"id": 1})


_ENDINGS = ["rollback", "failure", "interruption"]


def _ended(store: SimulatedTemporalStore, ending: str) -> contextlib.AbstractContextManager[None]:
    """A transaction over ``store`` ending as ``ending`` names, absorbing the
    exception it raises."""
    raised = {"failure": _Failed, "interruption": KeyboardInterrupt}.get(ending)

    @contextlib.contextmanager
    def ended() -> Generator[None]:
        with (
            contextlib.suppress(*(() if raised is None else (raised,))),
            store.transaction(rollback=ending == "rollback"),
        ):
            yield
            if raised is not None:
                raise raised

    return ended()


@pytest.mark.parametrize("ending", _ENDINGS)
def test_an_uncommitted_transaction_restores_every_row_and_flag(ending: str) -> None:
    single = {**_HEAD, "id": 2, "validEnd": INFINITY}
    store = SimulatedTemporalStore()
    store.seed_fixtures(POSITION, POSITION_ENTITY, [_HEAD, _TAIL, single])
    store.note_out_of_band_write()
    observed = store.predecessor_for(POSITION, POSITION_ENTITY, {"id": 2})
    assert observed is not None
    with _ended(store, ending):
        store.apply(POSITION, _close(_JUN))
        store.apply(POSITION, _revision(None, value=decimal.Decimal("300.00")))
        store.apply(POSITION, _close(None, key=2))
        store.apply(POSITION, _opening(2, _JAN, INFINITY, "10.00"))
        store.note_materialized_write(POSITION_ENTITY)
        assert _stored(store) == [(_TAIL["validStart"], INFINITY, decimal.Decimal("300.00"))]
        assert store.has_complete_stored_row(POSITION, POSITION_ENTITY, {"id": 2})
        assert store.moved_by_materialization(POSITION, POSITION_ENTITY, {"id": 2})
    assert _stored(store) == [_HEAD_ROW, _TAIL_ROW]
    assert store.predecessor_for(POSITION, POSITION_ENTITY, {"id": 2}) is observed
    assert dict(observed.predecessor.members) == single
    assert not store.has_complete_stored_row(POSITION, POSITION_ENTITY, {"id": 2})
    assert not store.moved_by_materialization(POSITION, POSITION_ENTITY, {"id": 2})
    # The restored rows are addressable again.
    store.apply(POSITION, _close(_JUN))
    assert _stored(store) == [_TAIL_ROW]


@pytest.mark.parametrize("ending", _ENDINGS)
def test_an_uncommitted_transaction_forgets_the_out_of_band_statements_it_ran(
    ending: str,
) -> None:
    store = SimulatedTemporalStore()
    with _ended(store, ending):
        store.note_out_of_band_write()
        assert not store.has_complete_stored_row(POSITION, POSITION_ENTITY, {"id": 1})
    assert store.has_complete_stored_row(POSITION, POSITION_ENTITY, {"id": 1})


# --------------------------------------------------------------------------- #
# A caller-addressed write's target read answers what the case state holds.   #
# --------------------------------------------------------------------------- #
ACCOUNT = models.load_models()["account"]
_ACCOUNT_ENTITY = ACCOUNT.entity(EntityIdentity("parallax.compatibility", "Account"))
assert _ACCOUNT_ENTITY is not None
ACCOUNT_ENTITY = _ACCOUNT_ENTITY
_ADA = {"id": 1, "owner": "Ada", "balance": "100.00", "version": 1}
_LINUS = {"id": 2, "owner": "Linus", "balance": "250.00", "version": 3}


def _accounts(*rows: Mapping[str, object]) -> SimulatedTemporalStore:
    store = SimulatedTemporalStore()
    store.seed_initial_rows(
        ACCOUNT,
        [
            (
                ACCOUNT_ENTITY,
                [_case_ingress.decode_case_row(row, ACCOUNT, ACCOUNT_ENTITY) for row in rows],
            )
        ],
    )
    return store


def _target(
    entity: EntityMetadata, key: int, valid_from: dt.datetime | None = None
) -> TargetReadRequest:
    return TargetReadRequest(
        entity,
        ObjectKey(entity.identity, (("id", key),)),
        valid_from,
        retains=valid_from is not None,
    )


type _Answer = tuple[int, list[dict[str, object]], Sequence[object | None] | None]


def _every_row(
    request: RowRequest,
    selection: EntityMemberSelection,
    rows: Iterator[tuple[object, ...]],
    absent: object,
    documents: Sequence[object | None] | None,
    root_count: int,
) -> _Answer:
    del request
    members = [PredecessorRow.over_row(selection, row, None, absent).members for row in rows]
    return (
        root_count,
        [{name: value for name, value in row.items() if value is not absent} for row in members],
        documents,
    )


def _read(store: SimulatedTemporalStore, model: Metamodel, request: RowRequest) -> _Answer:
    return store.acquisition(model)(request, _every_row)


def test_a_non_temporal_target_read_answers_the_initial_key_and_revision() -> None:
    store = _accounts(_ADA, _LINUS)
    assert _read(store, ACCOUNT, _target(ACCOUNT_ENTITY, 2)) == (
        1,
        [{"id": 2, "version": 3}],
        None,
    )


def test_a_non_temporal_target_read_counts_every_initial_row_of_its_key() -> None:
    # The count is the consumer's to judge before any revision: two stored rows
    # of one key are Cardinality Corruption whatever versions they hold.
    store = _accounts(_ADA, {**_ADA, "owner": "Twin", "version": 7})
    count, rows, _documents = _read(store, ACCOUNT, _target(ACCOUNT_ENTITY, 1))
    assert (count, [row["version"] for row in rows]) == (2, [1, 7])


@pytest.mark.parametrize("fixtures", [(), (_LINUS,)], ids=["no-fixtures", "other-key"])
def test_a_non_temporal_target_read_of_a_key_no_fixture_stores_finds_no_row(
    fixtures: tuple[Mapping[str, object], ...],
) -> None:
    assert _read(_accounts(*fixtures), ACCOUNT, _target(ACCOUNT_ENTITY, 1)) == (0, [], None)


def test_a_non_temporal_target_read_of_a_row_stored_without_its_revision_is_refused() -> None:
    store = _accounts({"id": 1, "owner": "Ada", "balance": "100.00"})
    with pytest.raises(SimulatedStoreError, match="without its revision"):
        _read(store, ACCOUNT, _target(ACCOUNT_ENTITY, 1))


def test_a_non_temporal_target_read_of_unseeded_state_is_refused_rather_than_empty() -> None:
    with pytest.raises(SimulatedStoreError, match="no current account"):
        _read(SimulatedTemporalStore(), ACCOUNT, _target(ACCOUNT_ENTITY, 1))


def _account(name: str) -> AttributeIdentity:
    return AttributeIdentity(ACCOUNT_ENTITY.identity, name)


def _account_update(key: int) -> PlannedUpdate:
    return PlannedUpdate(
        entity=ACCOUNT_ENTITY.identity,
        target=KeyTarget((_account("id"),), ((key,),)),
        assignments=PlannedAssignments(attributes={_account("balance"): decimal.Decimal("1.00")}),
        concurrency=Versioned(_account("version"), UNGATED),
        affected_rows=ExactCount(1, STALE_WRITE),
    )


def _account_insert(key: object) -> PlannedInsert:
    row = PlannedRow(
        attributes={
            _account("id"): key,
            _account("owner"): "New",
            _account("balance"): decimal.Decimal("0.00"),
            _account("version"): 1,
        }
    )
    return PlannedInsert(entity=ACCOUNT_ENTITY.identity, entries=(WriteRow(row, NEW_LINEAGE),))


_ACCOUNT_DELETE: Final = PlannedDelete(
    entity=ACCOUNT_ENTITY.identity,
    target=KeyTarget((_account("id"),), ((1,),)),
    concurrency=UNVERSIONED,
    affected_rows=ExactCount(1, MISSING_TARGET),
)
_CHANGES: Final[Mapping[str, tuple[Callable[[SimulatedTemporalStore], None], set[int]]]] = {
    "update": (lambda store: store.apply(ACCOUNT, _account_update(1)), {1}),
    "delete": (lambda store: store.apply(ACCOUNT, _ACCOUNT_DELETE), {1}),
    "insert": (lambda store: store.apply(ACCOUNT, _account_insert(3)), {3}),
    "generated-insert": (
        lambda store: store.apply(ACCOUNT, _account_insert(MAX_PLUS_ONE)),
        {1, 2, 3},
    ),
    "materialized": (lambda store: store.note_materialized_write(ACCOUNT_ENTITY), {1, 2, 3}),
    "out-of-band": (lambda store: store.note_out_of_band_write(), {1, 2, 3}),
}
"""Each change that may move an initial Account row, beside the keys whose
initial rows it leaves unknown."""


@pytest.mark.parametrize("change", list(_CHANGES))
def test_a_change_that_may_move_an_initial_row_leaves_its_target_read_unavailable(
    change: str,
) -> None:
    # A Non-Temporal row's later state is never simulated: once a change may
    # have moved it, its fixtures are neither returned stale nor taken as absent.
    store = _accounts(_ADA, _LINUS)
    applied, changed = _CHANGES[change]
    applied(store)
    for key in (1, 2, 3):
        request = _target(ACCOUNT_ENTITY, key)
        if key in changed:
            with pytest.raises(SimulatedStoreError, match="no current account"):
                _read(store, ACCOUNT, request)
        else:
            assert _read(store, ACCOUNT, request)[0] == (0 if key == 3 else 1)


@pytest.mark.parametrize("ending", _ENDINGS)
def test_an_uncommitted_transaction_restores_what_the_initial_rows_still_answer(
    ending: str,
) -> None:
    store = _accounts(_ADA, _LINUS)
    with _ended(store, ending):
        store.apply(ACCOUNT, _account_update(1))
        store.note_materialized_write(ACCOUNT_ENTITY)
    assert _read(store, ACCOUNT, _target(ACCOUNT_ENTITY, 1))[1] == [{"id": 1, "version": 1}]


@pytest.mark.parametrize("ending", _ENDINGS)
def test_out_of_band_statements_before_a_transaction_outlast_its_rollback(ending: str) -> None:
    store = _accounts(_ADA)
    store.note_out_of_band_write()
    with _ended(store, ending):
        pass
    with pytest.raises(SimulatedStoreError, match="no current account"):
        _read(store, ACCOUNT, _target(ACCOUNT_ENTITY, 1))


@pytest.mark.parametrize(
    ("valid_from", "values"),
    [
        pytest.param(_JAN, ["100.00"], id="head-start"),
        pytest.param(_MAR, ["100.00"], id="inside-head"),
        pytest.param(_JUN, ["200.00"], id="half-open-at-tail"),
        pytest.param(dt.datetime(2023, 1, 1, tzinfo=dt.UTC), [], id="before-every-rectangle"),
    ],
)
def test_a_temporal_target_read_selects_the_rectangles_current_at_its_valid_from(
    valid_from: dt.datetime, values: list[str]
) -> None:
    store = SimulatedTemporalStore()
    store.seed_fixtures(POSITION, POSITION_ENTITY, [_HEAD, _TAIL, {**_TAIL, "id": 2}])
    count, rows, documents = _read(store, POSITION, _target(POSITION_ENTITY, 1, valid_from))
    assert (count, documents) == (len(values), None)
    assert [row["value"] for row in rows] == [float(value) for value in values]
    assert all(row.keys() == _HEAD.keys() for row in rows)


def test_a_temporal_target_read_counts_every_rectangle_holding_its_valid_from() -> None:
    overlapping = {**_TAIL, "validStart": _MAR, "value": 300.00}
    store = SimulatedTemporalStore()
    store.seed_fixtures(POSITION, POSITION_ENTITY, [_HEAD, overlapping])
    assert _read(store, POSITION, _target(POSITION_ENTITY, 1, _JUN))[0] == 1
    assert (
        _read(store, POSITION, _target(POSITION_ENTITY, 1, dt.datetime(2024, 4, 1, tzinfo=dt.UTC)))[
            0
        ]
        == 2
    )


def test_a_completion_answers_the_retained_rows_without_reading_the_store(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = SimulatedTemporalStore()
    store.seed_fixtures(POSITION, POSITION_ENTITY, [_HEAD])
    taken: list[tuple[object, ...]] = []

    def retained(
        request: TargetReadRequest,
        selection: EntityMemberSelection,
        rows: Iterator[tuple[object, ...]],
        absent: object,
        documents: Sequence[object | None] | None,
        root_count: int,
    ) -> None:
        del request, selection, absent, documents, root_count
        taken.extend(rows)

    store.acquisition(POSITION)(_target(POSITION_ENTITY, 1, _MAR), retained)

    def unread(*_arguments: object) -> list[tuple[object, ...]]:
        raise AssertionError("a completion reads nothing")

    monkeypatch.setattr(SimulatedTemporalStore, "coverage_rows", unread)
    monkeypatch.setattr(SimulatedTemporalStore, "target_rows", unread)
    documents = (None,)
    completion = CompletionRequest(POSITION_ENTITY, _position("id"), tuple(taken), documents)
    count, rows, answered = _read(store, POSITION, completion)
    assert (count, answered) == (1, documents)
    assert rows[0]["value"] == _HEAD["value"]
