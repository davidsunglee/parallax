from __future__ import annotations

import json
from dataclasses import replace
from typing import cast

import pytest

import lifecycle_overhead
from parallax.conformance.budget import BudgetContract
from parallax.conformance.cost_envelope import validate
from snapshot_delivery_overhead import ChildReading, canary


def test_snapshot_member_has_a_valid_minimal_envelope() -> None:
    contract = BudgetContract.load()
    snapshot = canary(
        contract,
        lambda _request: ChildReading(
            1.0,
            "ms",
            (1.0,) * contract.timing_measured,
        ),
    )
    validate(snapshot)


def test_lifecycle_member_has_a_valid_measured_envelope() -> None:
    contract = BudgetContract.load()
    snapshot = canary(
        contract,
        lambda _request: ChildReading(
            1.0,
            "ms",
            (1.0,) * contract.timing_measured,
        ),
    )
    provenance = replace(snapshot.provenance, sampling={"timing": {"canary": 2}})
    envelope = lifecycle_overhead.canary(contract, provenance)
    validate(envelope)
    assert envelope.subject == "lifecycle-overhead"
    assert envelope.readings
    assert envelope.comparisons


def test_lifecycle_entrypoint_stdout_is_only_its_owned_envelope(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(lifecycle_overhead, "PAIRS", 2)
    monkeypatch.setattr(lifecycle_overhead, "WARMUP_PAIRS", 1)
    assert lifecycle_overhead.main([]) == 0
    captured = capsys.readouterr()
    document = cast("dict[str, object]", json.loads(captured.out))
    assert captured.err == ""
    assert document["subject"] == "lifecycle-overhead"
    validate(document)
