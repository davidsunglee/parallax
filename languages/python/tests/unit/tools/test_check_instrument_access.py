"""Unit tests for the whole-interpreter instrument access guard.

The reader's name is taken from the guard's own declared set rather than written
out, which keeps this module free of the calls it plants and pins the plants to
the set the guard actually enforces.
"""

from __future__ import annotations

from pathlib import Path

import pytest

import check_instrument_access as guard

READER = sorted(guard.WHOLE_INTERPRETER_READERS)[0]


def _findings(root: Path, source: str) -> list[guard.Finding]:
    (root / "test_probe.py").write_text(source)
    return guard.audit(root)


def test_a_test_carrying_the_boundary_calls_its_reader_legally(tmp_path: Path) -> None:
    source = (
        f"from memory_instruments import {READER}, {guard.BOUNDARY}\n\n\n"
        f"@{guard.BOUNDARY}\ndef test_probe():\n    {READER}(seam)\n"
    )
    assert _findings(tmp_path, source) == []


def test_the_real_test_tree_confines_whole_interpreter_readings() -> None:
    assert guard.main([]) == 0


def test_the_explicit_check_option_runs_the_same_guard(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(guard, "TESTS_ROOT", tmp_path)
    assert guard.main(["--check"]) == 0


@pytest.mark.parametrize(
    "source",
    [
        "import gc\n\ndef helper():\n    return gc.get_objects()\n",
        "from gc import get_objects as heap\n\ndef helper():\n    return heap()\n",
        "import gc\nread = gc.get_objects\n\ndef helper():\n    return read()\n",
        "import tracemalloc as tracer\n\ndef helper():\n    return tracer.get_traced_memory()\n",
        "from tracemalloc import take_snapshot as sample\n\ndef helper():\n    return sample()\n",
        (
            f"import gc\nfrom memory_instruments import {guard.BOUNDARY}\n\n"
            f"@{guard.BOUNDARY}\ndef test_probe():\n    gc.get_objects()\n"
        ),
    ],
    ids=[
        "heap-helper",
        "heap-alias",
        "reader-binding",
        "trace-module",
        "trace-alias",
        "decorated-raw",
    ],
)
def test_raw_readers_cannot_bypass_the_instrument_entry_points(tmp_path: Path, source: str) -> None:
    (tmp_path / "support.py").write_text(source)
    findings = guard.audit(tmp_path)
    assert len(findings) == 1
    assert "raw whole-interpreter reader" in findings[0].message


@pytest.mark.parametrize(
    "planted",
    [
        f"from memory_instruments import {READER}\n\n\ndef test_rogue():\n    {READER}(seam)\n",
        (
            "from tests.unit import memory_instruments as m\n\n\n"
            f"def test_rogue():\n    m.{READER}(seam)\n"
        ),
    ],
    ids=["imported-name", "module-attribute"],
)
def test_a_planted_reading_fails_the_gate(
    planted: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The plant goes into a scratch tree the audited root is pointed at, never
    into the real one: a canary interrupted mid-run would otherwise leave an
    untracked module behind and fail a sibling gate."""
    monkeypatch.setattr(guard, "TESTS_ROOT", tmp_path)
    assert guard.main([]) == 0

    (tmp_path / "test_rogue.py").write_text(planted)
    assert guard.main([]) == 1


@pytest.mark.parametrize(
    ("constant", "moved"),
    [
        ("FIXTURE", "evidence_elsewhere"),
        ("GATES", "spec/gates.yaml"),
        ("CAPTURES", "evidence/cost/*.json"),
    ],
)
def test_an_evidence_location_the_loaders_do_not_read_fails_the_gate(
    constant: str, moved: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(guard, "TESTS_ROOT", tmp_path)
    source = guard.EVIDENCE.read_text()
    declared = f'{constant}: Final = "'
    assert source.count(declared) == 1
    start = source.index(declared) + len(declared)
    planted = tmp_path / guard.EVIDENCE.name
    planted.write_text(f"{source[:start]}{moved}{source[source.index('"', start) :]}")
    monkeypatch.setattr(guard, "EVIDENCE", planted)
    assert guard.main([]) == 1
