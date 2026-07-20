"""Transaction-scoped reads (spec §5): force-flush, read-your-own-writes, read
locks, and the pin / history conversion seam shared with the module-level read
executor in ``parallax.snapshot.handle._read``.

Seeded in COR-42 Phase 2 with the ``_pin_from_milestone`` defensive-branch test;
the remaining reads regions arrive with the Phase 4-5 splits of
``test_transact.py``.
"""

from __future__ import annotations

import datetime as dt

import pytest

from parallax.conformance import models

# One of the three sanctioned private test seams (COR-42): `_pin_from_milestone`
# keeps its underscore because nothing outside `_read` calls it in production, so
# this defensive branch is only reachable from a test.
from parallax.snapshot.handle._read import (
    _pin_from_milestone,  # pyright: ignore[reportPrivateUsage]
)

pytestmark = pytest.mark.unit

_FIXED = dt.datetime(2024, 1, 1, tzinfo=dt.UTC)


def test_pin_from_milestone_skips_an_axis_absent_from_the_milestone_pin() -> None:
    # `_pin_from_milestone` is generic over any `Mapping` (not tied to how
    # `_edge_pin` always populates every declared axis in practice) — a
    # bitemporal entity's OWN as-of-attribute loop must skip an axis absent
    # from a given milestone's pin, not KeyError.
    position = models.load_models()["position"].entity("Position")
    pin = _pin_from_milestone(position, {"processingDate": _FIXED})
    assert pin.processing == _FIXED
    assert pin.business is None
