from __future__ import annotations

from collections.abc import Mapping
from typing import cast

from cost_report import MEMBERS, legacy_envelope
from parallax.conformance.budget import BudgetContract
from parallax.conformance.cost_envelope import validate
from snapshot_delivery_overhead import ChildReading, canary


def test_every_member_has_a_valid_minimal_envelope() -> None:
    snapshot = canary(
        BudgetContract.load(),
        lambda _request: ChildReading(1.0, "ms", (1.0,) * 9),
    ).document()
    provenance = cast("Mapping[str, object]", snapshot["provenance"])
    envelopes: list[Mapping[str, object]] = [snapshot]
    envelopes.extend(
        legacy_envelope(member, provenance, snapshot["authority"], "canary")
        for member in MEMBERS
        if not member.envelope
    )
    assert len(envelopes) == len(MEMBERS)
    for envelope in envelopes:
        validate(envelope)
