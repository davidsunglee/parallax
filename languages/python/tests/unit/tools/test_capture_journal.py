from __future__ import annotations

import json
from pathlib import Path

import pytest

import capture_journal
from capture_journal import CaptureJournal


def test_saved_reading_is_immutable_and_other_inputs_do_not_reuse_it(tmp_path: Path) -> None:
    journal = CaptureJournal(tmp_path, "snapshot", {"runtime": "3.15.0"})
    key = {"cell": "memory", "sample": 0}
    payload = {"value": 17.0, "samples": [17.0]}
    journal.store(key, payload)
    checkpoint = next(tmp_path.rglob("*.json"))
    original = checkpoint.read_bytes()
    assert journal.load(key) == payload
    journal.store(key, payload)
    with pytest.raises(ValueError, match="another result"):
        journal.store(key, {"value": 18.0})
    assert checkpoint.read_bytes() == original
    assert journal.load({"cell": "memory", "sample": 1}) is None
    assert CaptureJournal(tmp_path, "snapshot", {"runtime": "3.14.0"}).load(key) is None
    assert not list(tmp_path.rglob(".pending-*"))


def test_corrupt_checkpoint_is_refused_instead_of_remeasured(tmp_path: Path) -> None:
    journal = CaptureJournal(tmp_path, "snapshot", {})
    journal.store({"sample": 0}, {"value": 17.0})
    checkpoint = next(tmp_path.rglob("*.json"))
    document = json.loads(checkpoint.read_bytes())
    document["payload"]["value"] = 99.0
    checkpoint.write_text(json.dumps(document))
    with pytest.raises(ValueError, match="payload mismatch"):
        journal.load({"sample": 0})
    checkpoint.write_text("{")
    with pytest.raises(ValueError, match="invalid capture checkpoint"):
        journal.load({"sample": 0})


def test_interrupted_publish_keeps_previous_results_and_no_partial_entry(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    journal = CaptureJournal(tmp_path, "snapshot", {})
    journal.store({"sample": 0}, {"value": 17.0})

    def interrupted(_source: Path, _destination: Path) -> None:
        raise KeyboardInterrupt

    monkeypatch.setattr(capture_journal.os, "link", interrupted)
    with pytest.raises(KeyboardInterrupt):
        journal.store({"sample": 1}, {"value": 18.0})
    assert journal.load({"sample": 0}) == {"value": 17.0}
    assert journal.load({"sample": 1}) is None
    assert not list(tmp_path.rglob(".pending-*"))
