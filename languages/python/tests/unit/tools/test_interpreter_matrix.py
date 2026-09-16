from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

import interpreter_matrix as matrix


def test_supported_minors_close_the_declared_floor_from_below() -> None:
    minors = matrix.supported_minors()
    assert len(minors) == matrix.SUPPORTED_MINORS
    major, floor = (int(part) for part in minors[0].split("."))
    assert minors == tuple(f"{major}.{floor + above}" for above in range(len(minors)))
    assert matrix.CURRENT_MINOR in minors


def test_authority_minor_reads_the_contract_fingerprint() -> None:
    assert matrix.authority_minor({"cpython": "3.14.7"}) == "3.14"
    with pytest.raises(ValueError, match="does not name"):
        matrix.authority_minor({"cpython": "latest"})


def test_child_command_uses_the_current_interpreter_or_uv() -> None:
    script = Path("/tmp/reading.py")
    current = matrix.child_command(matrix.CURRENT_MINOR, script, ["case", "--flag"])
    other = matrix.child_command("9.99", script, ["case"])
    assert current == [sys.executable, str(script), "case", "--flag"]
    assert other == ["uv", "run", "--frozen", "--python", "9.99", "python", str(script), "case"]


def test_child_environment_isolates_another_minor_and_pins_hashing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PYTHONHOME", "wrong-runtime")
    monkeypatch.setenv("VIRTUAL_ENV", "wrong-environment")
    monkeypatch.setenv("COVERAGE_PROCESS_START", "coverage")
    current = matrix.child_environment(matrix.CURRENT_MINOR, "probe")
    other = matrix.child_environment("9.99", "probe")
    assert current["PYTHONHASHSEED"] == matrix.HASH_SEED
    assert current["PYTHONPATH"] == os.pathsep.join(entry for entry in sys.path if entry)
    assert "COVERAGE_PROCESS_START" not in current
    assert not {"PYTHONPATH", "PYTHONHOME", "VIRTUAL_ENV"} & other.keys()
    assert other["PYTHONHASHSEED"] == matrix.HASH_SEED
    assert other["UV_PROJECT_ENVIRONMENT"].endswith("parallax-probe-9.99")
