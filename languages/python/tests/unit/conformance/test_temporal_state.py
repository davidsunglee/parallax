"""``parallax.conformance.temporal_state.TemporalShadow`` unit tests.

The case-local tracker that supplies the engine's write lanes with an
observed current milestone is proven end to end
through the engine's own writeSequence/scenario tests
(``test_engine.py``, ``test_compile_sweep.py``, ``test_run_sweep.py``); this
module pins the tracker's OWN seam directly — fixture seeding, resolution,
the advance-from-plan-output invariant, and the abort's discard of a doomed
unit's advances — including the disambiguation refusal no reachable corpus case
witnesses.
"""

from __future__ import annotations

import datetime as dt
import decimal
from collections.abc import Mapping
from typing import cast

import pytest

from parallax.conformance import _case_ingress, models
from parallax.conformance.scripted_clock import FixedClock
from parallax.conformance.temporal_state import (
    AmbiguousObservationError,
    MilestoneEdgeError,
    TemporalShadow,
)
from parallax.core.base import INFINITY
from parallax.core.execution._planning import build_write_planner
from parallax.core.metamodel import AttributeIdentity, EntityIdentity
from parallax.core.temporal_read import TimeInterval
from parallax.core.unit_work import (
    PlanningRequest,
    SubjectActor,
    TransactionInstant,
    buffered_write,
    instructions,
)
from parallax.core.unit_work.instructions import KeyedWrite, PreparedWrite
from parallax.core.unit_work.write_planner import compose_writes
from parallax.core.write_plan import PredecessorRow, TemporalObservation
from parallax.core.write_plan.keys import ObjectKey, VersionedStateKey
from parallax.core.write_plan.plan import PlannedSteps, RangeAcquisition
from tests.unit.conformance._coverage_rows_support import coverage_members

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


def test_resolve_raises_when_more_than_one_current_milestone_is_tracked_for_a_pk() -> None:
    # Two rectangles for the SAME pk share an in_z (both current on Transaction
    # Time, different Valid Time windows) — the tracker refuses to guess which one
    # a later un-discriminated write means; a write that must address one of them
    # names the find it settles against instead (`TemporalShadow.resolve`'s own
    # docstring).
    shadow = TemporalShadow()
    shadow.seed_fixtures(
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
        shadow.resolve(POSITION, POSITION_ENTITY, {"id": 1})


def test_resolve_returns_none_for_a_pk_the_tracker_has_never_seen_open() -> None:
    # An insert's pk, or a genuinely unobserved close: the write itself
    # surfaces a conflict/stale error at execution, never this tracker.
    shadow = TemporalShadow()
    assert shadow.resolve(POSITION, POSITION_ENTITY, {"id": 99}) is None


def test_seed_fixtures_skips_a_row_not_current_on_transaction_time() -> None:
    # A historical (superseded) row — out_z finite — is never a later write's
    # observed row.
    shadow = TemporalShadow()
    shadow.seed_fixtures(
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
    assert shadow.resolve(POSITION, POSITION_ENTITY, {"id": 1}) is None


@pytest.mark.parametrize(
    "valid_start", [INFINITY, "infinity", "2024-01-01T00:00:00+00:00", 20240101]
)
def test_an_axis_start_that_is_not_a_finite_instant_is_refused(valid_start: object) -> None:
    # A milestone's edge is its from-instant per axis. The open bound belongs to
    # an axis END, and neither a bare number nor an unmanaged instant spelling is
    # a managed coordinate — each would key a slot no read can ever match, so all
    # are refused where the slot is keyed.
    with pytest.raises(MilestoneEdgeError, match="finite instant"):
        TemporalShadow().seed_fixtures(
            POSITION, POSITION_ENTITY, [{**_HEAD, "validStart": valid_start}]
        )


def _planned(
    entity_name: str, members: dict[str, object], *, valid_from: str, at: str
) -> PlannedSteps:
    """The Write Plan an insert of ``members`` produces, through the SAME
    ``build_write_planner`` factory the engine's own write lanes plan with — so
    what the ledger tracks is what a flush would actually write."""
    instruction = instructions.deserialize(
        {"mutation": "insert", "entity": entity_name, "rows": [members], "validFrom": valid_from}
    )
    assert isinstance(instruction, KeyedWrite)  # a `rows` document is a keyed write
    prepared = instructions.prepare_wire_write(instruction, POSITION)
    return (
        build_write_planner(POSITION)
        .finalize(
            PlanningRequest(
                actor_identity=SubjectActor("unattributed"),
                transaction_instant=TransactionInstant(FixedClock(dt.datetime.fromisoformat(at))),
                concurrency="locking",
                buffered_writes=[prepared],
            )
        )
        .plan.steps
    )


def test_retire_drops_only_the_milestone_the_write_observed() -> None:
    # A rectangle split closes ONE rectangle and chains its successors; the key's
    # other current rectangle was neither closed nor superseded by that write, so
    # it stays tracked. Under a pk-keyed tracker the successors replace the whole
    # key and the untouched rectangle silently disappears.
    shadow = TemporalShadow()
    shadow.seed_fixtures(POSITION, POSITION_ENTITY, [_HEAD, _TAIL])
    shadow.retire(
        POSITION, POSITION_ENTITY, TemporalObservation(predecessor=PredecessorRow(members=_TAIL))
    )
    survivor = shadow.resolve(POSITION, POSITION_ENTITY, {"id": 1})
    assert survivor is not None
    assert survivor.predecessor.member("value") == 100.00


@pytest.mark.parametrize(
    ("value", "kept"), [("100.00", True), ("150.00", False)], ids=["kept", "closed"]
)
def test_a_milestone_no_step_closes_is_tracked_again_after_its_write_resolved(
    value: str, kept: bool
) -> None:
    shadow = TemporalShadow()
    shadow.seed_fixtures(POSITION, POSITION_ENTITY, [_HEAD])
    observed = shadow.resolve(POSITION, POSITION_ENTITY, {"id": 1})
    assert observed is not None
    shadow.retire(POSITION, POSITION_ENTITY, observed)
    prepared = instructions.prepare_wire_write(
        KeyedWrite(
            "updateUntil",
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
            PlanningRequest(
                actor_identity=SubjectActor("unattributed"),
                transaction_instant=TransactionInstant(
                    FixedClock(dt.datetime(2024, 9, 1, tzinfo=dt.UTC))
                ),
                concurrency="locking",
                buffered_writes=compose_writes(POSITION, [buffered_write(prepared, observed)]),
            )
        )
        .plan.steps
    )
    shadow.keep_unchanged(POSITION, steps, [(POSITION_ENTITY, observed)])
    assert (shadow.resolve(POSITION, POSITION_ENTITY, {"id": 1}) is observed) is kept


def test_a_doomed_units_retirement_and_re_accounting_are_both_discarded() -> None:
    # `retire` drops a milestone and `_track` clears the doubt out-of-band
    # statements left on its slot. A doomed unit does both and then aborts, so
    # both must be undone: the milestone is tracked again AND is once more a
    # milestone `accounts_for` refuses, since the row the abort restored is the
    # one those statements may have overtaken, not the one the plan opened.
    shadow = TemporalShadow()
    shadow.seed_fixtures(POSITION, POSITION_ENTITY, [_HEAD])
    shadow.note_out_of_band_write()
    assert not shadow.accounts_for(POSITION, POSITION_ENTITY, _HEAD)
    observed = shadow.resolve(POSITION, POSITION_ENTITY, {"id": 1})
    assert observed is not None
    with shadow.staged(doomed=True):
        shadow.retire(POSITION, POSITION_ENTITY, observed)
        shadow.seed_fixtures(POSITION, POSITION_ENTITY, [_HEAD])
        assert shadow.accounts_for(POSITION, POSITION_ENTITY, _HEAD)
    assert shadow.resolve(POSITION, POSITION_ENTITY, {"id": 1}) is not None
    assert not shadow.accounts_for(POSITION, POSITION_ENTITY, _HEAD)


def test_track_opened_tracks_the_milestones_the_plan_actually_opens() -> None:
    # The tracker advances from the plan the write lane already produced, so a
    # plain insert's one opened rectangle is tracked with the framework-owned
    # interval bounds the plan stamped on it — never a second expansion of the
    # same topology computed beside it.
    shadow = TemporalShadow()
    shadow.track_opened(
        POSITION,
        _planned(
            "Position",
            {"id": 1, "acctNum": "A", "value": "100.00"},
            valid_from="2024-01-01T00:00:00Z",
            at="2024-01-01T00:00:00+00:00",
        ),
    )
    observation = shadow.resolve(POSITION, POSITION_ENTITY, {"id": 1})
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


def test_track_opened_ignores_a_non_temporal_plan() -> None:
    # A non-temporal insert opens no milestone, so a ledger entry for it would
    # answer no question a later step can ask.
    shadow = TemporalShadow()
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
    plan = (
        build_write_planner(account)
        .finalize(
            PlanningRequest(
                actor_identity=SubjectActor("unattributed"),
                transaction_instant=TransactionInstant(
                    FixedClock(dt.datetime(2024, 1, 1, tzinfo=dt.UTC))
                ),
                concurrency="locking",
                buffered_writes=[prepared],
            )
        )
        .plan
    )
    shadow.track_opened(account, plan.steps)
    entity = account.entity(EntityIdentity("parallax.compatibility", "Account"))
    assert entity is not None
    assert shadow.resolve(account, entity, {"id": 1}) is None


def test_two_tracked_milestones_of_one_key_sharing_an_edge_are_refused() -> None:
    # An edge names exactly one milestone, so a state holding two current
    # milestones of one key at one edge is unaddressable: keeping the later would
    # hand every subsequent step a row no case selected.
    shadow = TemporalShadow()
    twin = {**_TAIL, "value": 300.00, "validStart": _HEAD["validStart"]}
    with pytest.raises(AmbiguousObservationError, match="carry the edge"):
        shadow.seed_fixtures(POSITION, POSITION_ENTITY, [_HEAD, twin])


def _rectangles(
    *spans: tuple[int, str, str | None, str],
) -> PlannedSteps:
    """The plan opening one rectangle per ``(id, validFrom, until, value)``."""
    entries: list[PreparedWrite] = []
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
            PlanningRequest(
                actor_identity=SubjectActor("unattributed"),
                transaction_instant=TransactionInstant(
                    FixedClock(dt.datetime(2024, 1, 1, tzinfo=dt.UTC))
                ),
                concurrency="locking",
                buffered_writes=entries,
            )
        )
        .plan.steps
    )


def _acquisition(valid_from: dt.datetime, until: dt.datetime | None) -> RangeAcquisition:
    key = AttributeIdentity(POSITION_ENTITY.identity, "id")
    return RangeAcquisition(
        entity=POSITION_ENTITY,
        key_attribute=key,
        key_value=1,
        valid_time_window=TimeInterval(valid_from, INFINITY if until is None else until),
        locking=False,
    )


def test_coverage_answers_the_tracked_rectangles_of_one_object_inside_the_window() -> None:
    shadow = TemporalShadow()
    shadow.track_opened(
        POSITION,
        _rectangles(
            (1, "2024-01-01T00:00:00Z", "2024-03-01T00:00:00Z", "1.00"),
            (1, "2024-03-01T00:00:00Z", "2024-06-01T00:00:00Z", "2.00"),
            (1, "2024-06-01T00:00:00Z", None, "3.00"),
            (2, "2024-01-01T00:00:00Z", None, "9.00"),
        ),
    )
    covered = shadow.coverage(
        POSITION,
        _acquisition(
            dt.datetime(2024, 4, 1, tzinfo=dt.UTC), dt.datetime(2024, 6, 1, tzinfo=dt.UTC)
        ),
    )
    assert [row["value"] for row in coverage_members(covered)] == [decimal.Decimal("2.00")]


def test_coverage_reaches_a_tracked_opening_whose_end_is_the_open_bound() -> None:
    shadow = TemporalShadow()
    shadow.track_opened(
        POSITION,
        _rectangles(
            (1, "2024-01-01T00:00:00Z", "2024-03-01T00:00:00Z", "1.00"),
            (1, "2024-03-01T00:00:00Z", None, "2.00"),
        ),
    )
    covered = shadow.coverage(POSITION, _acquisition(dt.datetime(2024, 4, 1, tzinfo=dt.UTC), None))
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
    shadow = TemporalShadow()
    shadow.seed_fixtures(
        POSITION,
        POSITION_ENTITY,
        [_case_ingress.decode_case_row(fixture, POSITION, POSITION_ENTITY)],
    )
    covered = shadow.coverage(
        POSITION,
        _acquisition(
            dt.datetime(2024, 9, 1, tzinfo=dt.UTC), dt.datetime(2024, 10, 1, tzinfo=dt.UTC)
        ),
    )
    assert [(row["validEnd"], row["txEnd"]) for row in coverage_members(covered)] == [
        (INFINITY, INFINITY)
    ]


def test_coverage_reaches_a_database_observation_kept_unchanged() -> None:
    # A grouped read's observation carries the port's managed open bound, and a
    # write that leaves the milestone unchanged keeps tracking that observation.
    observed = TemporalObservation(predecessor=PredecessorRow(members=_TAIL))
    shadow = TemporalShadow()
    shadow.keep_unchanged(POSITION, (), [(POSITION_ENTITY, observed)])
    covered = shadow.coverage(POSITION, _acquisition(dt.datetime(2024, 7, 1, tzinfo=dt.UTC), None))
    assert [dict(row) for row in coverage_members(covered)] == [dict(observed.predecessor.members)]


def test_retiring_a_state_with_no_milestone_leaves_the_tracker_alone() -> None:
    shadow = TemporalShadow()
    shadow.track_opened(
        POSITION,
        _rectangles((1, "2024-01-01T00:00:00Z", None, "1.00")),
        retired=(VersionedStateKey(ObjectKey(POSITION_ENTITY.identity, (("id", 1),)), 1),),
    )
    assert shadow.resolve(POSITION, POSITION_ENTITY, {"id": 1}) is not None


def test_coverage_answers_a_tracked_milestones_value_objects_positionally() -> None:
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
    shadow = TemporalShadow()
    shadow.keep_unchanged(
        model, (), [(entity, TemporalObservation(predecessor=PredecessorRow(members)))]
    )
    covered = shadow.coverage(
        model,
        RangeAcquisition(
            entity=entity,
            key_attribute=AttributeIdentity(entity.identity, "id"),
            key_value=7,
            valid_time_window=None,
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
        TemporalShadow().coverage(
            POSITION, _acquisition(dt.datetime(2024, 1, 1, tzinfo=dt.UTC), None)
        )
        is None
    )
