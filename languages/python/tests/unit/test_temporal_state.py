"""``parallax.conformance.temporal_state.TemporalShadow`` unit tests.

The case-local tracker that supplies the engine's write lanes with an
observed current milestone (COR-3 Phase 8 increment 4) is proven end to end
through the engine's own writeSequence/scenario/conflict tests
(``test_engine.py``, ``test_compile_sweep.py``, ``test_run_sweep.py``); this
module pins the tracker's OWN seam directly — fixture seeding, resolution,
and the advance-from-plan-output invariant — including the disambiguation
refusal no reachable corpus case witnesses.
"""

from __future__ import annotations

import pytest

from parallax.conformance import models
from parallax.conformance.temporal_state import AmbiguousObservationError, TemporalShadow
from parallax.core.unit_work import KeyedWrite

pytestmark = pytest.mark.unit

POSITION = models.load_models()["position"]


def test_resolve_raises_when_more_than_one_current_milestone_is_tracked_for_a_pk() -> None:
    # m-bitemp-write-004/005's own shape: two rectangles for the SAME pk share
    # an in_z (both current on processing, different business windows) — the
    # tracker refuses to guess which one a later un-discriminated write means;
    # disambiguation by business-from is a conflict-shape-only mechanism this
    # increment reaches through the case's own explicit fields, never this
    # tracker (`TemporalShadow.resolve`'s own docstring).
    shadow = TemporalShadow()
    shadow.seed_fixtures(
        POSITION,
        "Position",
        [
            {
                "id": 1,
                "acctNum": "A",
                "value": 100.00,
                "businessFrom": "2024-01-01T00:00:00+00:00",
                "businessTo": "2024-06-01T00:00:00+00:00",
                "processingFrom": "2024-01-01T00:00:00+00:00",
                "processingTo": "infinity",
            },
            {
                "id": 1,
                "acctNum": "A",
                "value": 200.00,
                "businessFrom": "2024-06-01T00:00:00+00:00",
                "businessTo": "infinity",
                "processingFrom": "2024-01-01T00:00:00+00:00",
                "processingTo": "infinity",
            },
        ],
    )
    with pytest.raises(AmbiguousObservationError, match="2 current milestones"):
        shadow.resolve(POSITION, "Position", {"id": 1})


def test_resolve_returns_none_for_a_pk_the_tracker_has_never_seen_open() -> None:
    # An insert's pk, or a genuinely unobserved close: the write itself
    # surfaces a conflict/stale error at execution, never this tracker.
    shadow = TemporalShadow()
    assert shadow.resolve(POSITION, "Position", {"id": 99}) is None


def test_seed_fixtures_skips_a_row_not_current_on_processing() -> None:
    # A historical (superseded) row — out_z finite — is never a later write's
    # observed row.
    shadow = TemporalShadow()
    shadow.seed_fixtures(
        POSITION,
        "Position",
        [
            {
                "id": 1,
                "acctNum": "A",
                "value": 100.00,
                "businessFrom": "2024-01-01T00:00:00+00:00",
                "businessTo": "infinity",
                "processingFrom": "2024-01-01T00:00:00+00:00",
                "processingTo": "2024-06-01T00:00:00+00:00",
            }
        ],
    )
    assert shadow.resolve(POSITION, "Position", {"id": 1}) is None


def test_advance_replaces_tracked_state_with_the_newly_opened_rows() -> None:
    # The SAME pure planning function (`bitemp_write.plan`) the render seam
    # calls computes what to track next — a plain insert opens one rectangle.
    shadow = TemporalShadow()
    insert = KeyedWrite(
        "insert",
        "Position",
        ({"id": 1, "acctNum": "A", "value": 100.00},),
        business_from="2024-01-01T00:00:00+00:00",
    )
    shadow.advance(POSITION, "Position", insert, "2024-01-01T00:00:00+00:00", None)
    observation = shadow.resolve(POSITION, "Position", {"id": 1})
    assert observation is not None
    assert observation.in_z == "2024-01-01T00:00:00+00:00"
    assert observation.business_from == "2024-01-01T00:00:00+00:00"
    assert observation.business_to == "infinity"
    assert observation.payload == {"id": 1, "acctNum": "A", "value": 100.00}
