from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path
from typing import cast

import pytest

import lifecycle_overhead
from durations import Spans
from interpreter_matrix import CURRENT_MINOR, current_identity, load_metadata
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


def test_lifecycle_entrypoint_writes_an_empty_sidecar_and_refuses_other_arguments(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(lifecycle_overhead, "PAIRS", 2)
    monkeypatch.setattr(lifecycle_overhead, "WARMUP_PAIRS", 1)
    sidecar = tmp_path / "durations.json"
    assert lifecycle_overhead.main(["--durations", str(sidecar)]) == 0
    captured = capsys.readouterr()
    document = cast("dict[str, object]", json.loads(captured.out))
    assert captured.err == ""
    assert document["subject"] == "lifecycle-overhead"
    validate(document)
    spans = Spans.load(sidecar)
    assert spans.spans == ()
    assert spans.unavailable == ()
    assert lifecycle_overhead.main(["unexpected"]) == 2
    assert "usage:" in capsys.readouterr().err


def test_lifecycle_entrypoint_reports_an_unwritable_sidecar_and_still_measures(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(lifecycle_overhead, "PAIRS", 2)
    monkeypatch.setattr(lifecycle_overhead, "WARMUP_PAIRS", 1)
    durations = tmp_path / "durations.json"
    metadata = tmp_path / "metadata.json"
    durations.mkdir()
    metadata.mkdir()
    assert (
        lifecycle_overhead.main(["--durations", str(durations), "--metadata", str(metadata)]) == 0
    )
    captured = capsys.readouterr()
    validate(cast("dict[str, object]", json.loads(captured.out)))
    assert captured.err.splitlines() == [
        f"telemetry sidecar {durations} was not written: [Errno 21] Is a directory: '{durations}'",
        f"telemetry sidecar {metadata} was not written: [Errno 21] Is a directory: '{metadata}'",
    ]


def test_lifecycle_entrypoint_records_the_interpreter_it_measures_in(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(lifecycle_overhead, "PAIRS", 2)
    monkeypatch.setattr(lifecycle_overhead, "WARMUP_PAIRS", 1)
    metadata = tmp_path / "metadata.json"
    assert lifecycle_overhead.main(["--metadata", str(metadata)]) == 0
    captured = capsys.readouterr()
    assert captured.err == ""
    document = cast("dict[str, object]", json.loads(captured.out))
    validate(document)
    assert load_metadata(metadata) == {CURRENT_MINOR: current_identity()}
    provenance = cast("dict[str, object]", document["provenance"])
    assert provenance["cpython"] == current_identity().version
