"""``parallax.conformance.temporal_state.TemporalShadow`` unit tests.

The case-local tracker that supplies the engine's write lanes with an
observed current milestone is proven end to end
through the engine's own writeSequence/scenario/conflict tests
(``test_engine.py``, ``test_compile_sweep.py``, ``test_run_sweep.py``); this
module pins the tracker's OWN seam directly — fixture seeding, resolution,
the advance-from-plan-output invariant, and the abort's discard of a doomed
unit's advances — including the disambiguation refusal no reachable corpus case
witnesses.
"""

from __future__ import annotations

import datetime as dt
import decimal

import pytest

from parallax.conformance import models
from parallax.conformance.temporal_state import (
    AmbiguousObservationError,
    MilestoneEdgeError,
    TemporalShadow,
    observed_close_coordinates,
    observed_edge,
)
from parallax.core.metamodel import EntityIdentity
from parallax.core.unit_work import (
    FixedClock,
    PlanningRequest,
    SubjectIdentity,
    TransactionInstant,
    WritePlan,
    buffered_write,
    instructions,
)
from parallax.snapshot.handle import build_write_planner

POSITION = models.load_models()["position"]
_POSITION_ENTITY = POSITION.entity(EntityIdentity("parallax.compatibility", "Position"))
assert _POSITION_ENTITY is not None
POSITION_ENTITY = _POSITION_ENTITY

BALANCE = models.load_models()["balance"]
_BALANCE_ENTITY = BALANCE.entity(EntityIdentity("parallax.compatibility", "Balance"))
assert _BALANCE_ENTITY is not None
BALANCE_ENTITY = _BALANCE_ENTITY

# The two rectangles of one key that are current on Transaction Time at once
# (m-bitemp-write-017's own fixture pair): identical primary key, identical open
# Transaction-Time bound, identical `txStart`. Only their edges tell them apart.
_HEAD = {
    "id": 1,
    "acctNum": "A",
    "value": 100.00,
    "validStart": "2024-01-01T00:00:00+00:00",
    "validEnd": "2024-06-01T00:00:00+00:00",
    "txStart": "2024-04-01T00:00:00+00:00",
    "txEnd": "infinity",
}
_TAIL = {
    "id": 1,
    "acctNum": "A",
    "value": 200.00,
    "validStart": "2024-06-01T00:00:00+00:00",
    "validEnd": "infinity",
    "txStart": "2024-04-01T00:00:00+00:00",
    "txEnd": "infinity",
}


def test_resolve_raises_when_more_than_one_current_milestone_is_tracked_for_a_pk() -> None:
    # m-bitemp-write-004/005's own shape: two rectangles for the SAME pk share
    # an in_z (both current on Transaction Time, different Valid Time windows) — the
    # tracker refuses to guess which one a later un-discriminated write means;
    # disambiguation by Valid Time-from is a conflict-shape-only mechanism this
    # increment reaches through the case's own explicit fields, never this
    # tracker (`TemporalShadow.resolve`'s own docstring).
    shadow = TemporalShadow()
    shadow.seed_fixtures(
        POSITION,
        POSITION_ENTITY,
        [
            {
                "id": 1,
                "acctNum": "A",
                "value": 100.00,
                "validStart": "2024-01-01T00:00:00+00:00",
                "validEnd": "2024-06-01T00:00:00+00:00",
                "txStart": "2024-01-01T00:00:00+00:00",
                "txEnd": "infinity",
            },
            {
                "id": 1,
                "acctNum": "A",
                "value": 200.00,
                "validStart": "2024-06-01T00:00:00+00:00",
                "validEnd": "infinity",
                "txStart": "2024-01-01T00:00:00+00:00",
                "txEnd": "infinity",
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
                "validStart": "2024-01-01T00:00:00+00:00",
                "validEnd": "infinity",
                "txStart": "2024-01-01T00:00:00+00:00",
                "txEnd": "2024-06-01T00:00:00+00:00",
            }
        ],
    )
    assert shadow.resolve(POSITION, POSITION_ENTITY, {"id": 1}) is None


def test_resolve_by_edge_selects_the_named_one_of_a_keys_current_rectangles() -> None:
    # The refusal above is not a limit on what a key may hold — it is a refusal to
    # guess for an input that named nothing. Naming a rectangle's own edge picks
    # it out of the same pair the un-named lookup refuses, and the OTHER edge
    # picks the other, so the discriminator is the observation rather than the key.
    shadow = TemporalShadow()
    shadow.seed_fixtures(POSITION, POSITION_ENTITY, [_HEAD, _TAIL])
    head = shadow.resolve(
        POSITION,
        POSITION_ENTITY,
        {"id": 1},
        observed_edge(
            POSITION,
            POSITION_ENTITY,
            valid_start="2024-01-01T00:00:00+00:00",
            tx_start="2024-04-01T00:00:00+00:00",
        ),
    )
    tail = shadow.resolve(
        POSITION,
        POSITION_ENTITY,
        {"id": 1},
        observed_edge(
            POSITION,
            POSITION_ENTITY,
            valid_start="2024-06-01T00:00:00+00:00",
            tx_start="2024-04-01T00:00:00+00:00",
        ),
    )
    assert head is not None and tail is not None
    assert head.predecessor.member("value") == 100.00
    assert tail.predecessor.member("value") == 200.00


def test_resolve_by_edge_returns_none_for_an_edge_no_current_milestone_carries() -> None:
    # A named milestone that is not there is a miss, never a fallback to whichever
    # rectangle the key happens to hold.
    shadow = TemporalShadow()
    shadow.seed_fixtures(POSITION, POSITION_ENTITY, [_HEAD, _TAIL])
    assert (
        shadow.resolve(
            POSITION,
            POSITION_ENTITY,
            {"id": 1},
            observed_edge(
                POSITION,
                POSITION_ENTITY,
                valid_start="2023-01-01T00:00:00+00:00",
                tx_start="2024-04-01T00:00:00+00:00",
            ),
        )
        is None
    )


def test_two_spellings_of_one_instant_name_the_same_edge() -> None:
    # An edge is compared as an INSTANT, not as a string, so a coordinate spelled
    # in another offset names the milestone it denotes rather than missing it.
    shadow = TemporalShadow()
    shadow.seed_fixtures(POSITION, POSITION_ENTITY, [_HEAD, _TAIL])
    observation = shadow.resolve(
        POSITION,
        POSITION_ENTITY,
        {"id": 1},
        observed_edge(
            POSITION,
            POSITION_ENTITY,
            valid_start="2023-12-31T19:00:00-05:00",
            tx_start=dt.datetime(2024, 4, 1, tzinfo=dt.UTC),
        ),
    )
    assert observation is not None
    assert observation.predecessor.member("value") == 100.00


def test_an_edge_naming_fewer_axes_than_the_target_declares_is_refused() -> None:
    # A Bitemporal milestone's edge is a coordinate per axis; one axis alone
    # selects no milestone, so it is refused rather than resolved partially.
    with pytest.raises(MilestoneEdgeError, match="valid-time start is missing"):
        observed_edge(
            POSITION,
            POSITION_ENTITY,
            valid_start=None,
            tx_start="2024-04-01T00:00:00+00:00",
        )


@pytest.mark.parametrize("valid_start", ["infinity", 20240101])
def test_an_axis_start_that_is_not_a_finite_instant_is_refused(valid_start: object) -> None:
    # A milestone's edge is its from-instant per axis. The open bound belongs to
    # an axis END, and a bare number is no coordinate at all — either would key a
    # slot no read can ever match, so both are refused where the edge is built.
    with pytest.raises(MilestoneEdgeError, match="finite instant"):
        observed_edge(
            POSITION,
            POSITION_ENTITY,
            valid_start=valid_start,
            tx_start="2024-04-01T00:00:00+00:00",
        )


def test_close_coordinates_come_from_the_one_observed_milestone() -> None:
    # The address's Valid-Time end and the gate's Transaction-Time start are read
    # off ONE predecessor, so a close cannot address one rectangle and gate on
    # another. A Transaction-Time-Only target has no Valid-Time axis to bound.
    shadow = TemporalShadow()
    shadow.seed_fixtures(POSITION, POSITION_ENTITY, [_HEAD, _TAIL])
    head = shadow.resolve(
        POSITION,
        POSITION_ENTITY,
        {"id": 1},
        observed_edge(
            POSITION,
            POSITION_ENTITY,
            valid_start="2024-01-01T00:00:00+00:00",
            tx_start="2024-04-01T00:00:00+00:00",
        ),
    )
    assert head is not None
    assert observed_close_coordinates(POSITION, POSITION_ENTITY, head) == (
        "2024-06-01T00:00:00+00:00",
        "2024-04-01T00:00:00+00:00",
    )

    audit = TemporalShadow()
    audit.seed_fixtures(
        BALANCE,
        BALANCE_ENTITY,
        [
            {
                "id": 1,
                "acctNum": "A",
                "value": 150.00,
                "txStart": "2024-06-01T00:00:00+00:00",
                "txEnd": "infinity",
            }
        ],
    )
    current = audit.resolve(BALANCE, BALANCE_ENTITY, {"id": 1})
    assert current is not None
    assert observed_close_coordinates(BALANCE, BALANCE_ENTITY, current) == (
        None,
        "2024-06-01T00:00:00+00:00",
    )


def _planned(
    entity_name: str, members: dict[str, object], *, valid_from: str, at: str
) -> WritePlan:
    """The Write Plan an insert of ``members`` produces, through the SAME
    ``build_write_planner`` factory the engine's own write lanes plan with — so
    what the ledger tracks is what a flush would actually write."""
    instruction = instructions.deserialize(
        {"mutation": "insert", "entity": entity_name, "rows": [members], "validFrom": valid_from}
    )
    prepared = instructions.prepare_wire_write(instruction, POSITION)
    return build_write_planner(POSITION).plan(
        PlanningRequest(
            subject_identity=SubjectIdentity("unattributed"),
            transaction_instant=TransactionInstant(FixedClock(dt.datetime.fromisoformat(at))),
            concurrency="locking",
            buffered_writes=[buffered_write(prepared, None)],
        )
    )


def test_retire_drops_only_the_milestone_the_write_observed() -> None:
    # A rectangle split closes ONE rectangle and chains its successors; the key's
    # other current rectangle was neither closed nor superseded by that write, so
    # it stays tracked. Under a pk-keyed tracker the successors replace the whole
    # key and the untouched rectangle silently disappears.
    shadow = TemporalShadow()
    shadow.seed_fixtures(POSITION, POSITION_ENTITY, [_HEAD, _TAIL])
    tail_edge = observed_edge(
        POSITION,
        POSITION_ENTITY,
        valid_start="2024-06-01T00:00:00+00:00",
        tx_start="2024-04-01T00:00:00+00:00",
    )
    observed = shadow.resolve(POSITION, POSITION_ENTITY, {"id": 1}, tail_edge)
    assert observed is not None
    shadow.retire(POSITION, POSITION_ENTITY, observed)
    assert shadow.resolve(POSITION, POSITION_ENTITY, {"id": 1}, tail_edge) is None
    survivor = shadow.resolve(
        POSITION,
        POSITION_ENTITY,
        {"id": 1},
        observed_edge(
            POSITION,
            POSITION_ENTITY,
            valid_start="2024-01-01T00:00:00+00:00",
            tx_start="2024-04-01T00:00:00+00:00",
        ),
    )
    assert survivor is not None
    assert survivor.predecessor.member("value") == 100.00


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
        "validEnd": "infinity",
        "txStart": dt.datetime(2024, 1, 1, tzinfo=dt.UTC),
        "txEnd": "infinity",
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
    account = models.load_models()["account"]
    prepared = instructions.prepare_wire_write(instruction, account)
    plan = build_write_planner(account).plan(
        PlanningRequest(
            subject_identity=SubjectIdentity("unattributed"),
            transaction_instant=TransactionInstant(
                FixedClock(dt.datetime(2024, 1, 1, tzinfo=dt.UTC))
            ),
            concurrency="locking",
            buffered_writes=[buffered_write(prepared, None)],
        )
    )
    shadow.track_opened(account, plan)
    entity = account.entity(EntityIdentity("parallax.compatibility", "Account"))
    assert entity is not None
    assert shadow.resolve(account, entity, {"id": 1}) is None


def test_an_edge_naming_an_axis_the_target_does_not_declare_is_refused() -> None:
    # `observedValidStart` names a Valid-Time start, and a Transaction-Time-Only
    # target's milestones have none. Dropping the coordinate would resolve the
    # write against a milestone the author never named, so the edge is refused
    # where it is built rather than silently narrowed to the declared axis.
    with pytest.raises(MilestoneEdgeError, match="declares no valid-time axis"):
        observed_edge(
            BALANCE,
            BALANCE_ENTITY,
            valid_start="2024-01-01T00:00:00+00:00",
            tx_start="2024-04-01T00:00:00+00:00",
        )


def test_two_tracked_milestones_of_one_key_sharing_an_edge_are_refused() -> None:
    # An edge names exactly one milestone, so a state holding two current
    # milestones of one key at one edge is unaddressable: keeping the later would
    # hand every subsequent step a row no case selected.
    shadow = TemporalShadow()
    twin = {**_TAIL, "value": 300.00, "validStart": _HEAD["validStart"]}
    with pytest.raises(AmbiguousObservationError, match="carry the edge"):
        shadow.seed_fixtures(POSITION, POSITION_ENTITY, [_HEAD, twin])


def test_a_transaction_time_only_targets_edge_names_its_one_declared_axis() -> None:
    # An edge is a coordinate per DECLARED axis, so a Transaction-Time-Only
    # target's edge carries the Transaction-Time start alone and still selects
    # its milestone — the same shared derivation the tracker keys its own slots
    # by, one axis narrower.
    shadow = TemporalShadow()
    shadow.seed_fixtures(
        BALANCE,
        BALANCE_ENTITY,
        [
            {
                "id": 1,
                "acctNum": "A",
                "value": 150.00,
                "txStart": "2024-06-01T00:00:00+00:00",
                "txEnd": "infinity",
            }
        ],
    )
    observation = shadow.resolve(
        BALANCE,
        BALANCE_ENTITY,
        {"id": 1},
        observed_edge(
            BALANCE, BALANCE_ENTITY, valid_start=None, tx_start="2024-06-01T00:00:00+00:00"
        ),
    )
    assert observation is not None
    assert observation.predecessor.member("value") == 150.00
