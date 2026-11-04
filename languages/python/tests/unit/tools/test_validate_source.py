from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

import validate_source as source


def _inputs(tmp_path: Path) -> tuple[Path, Path, Path]:
    sdists = tmp_path / "sdists"
    sdists.mkdir()
    for name in source.PRODUCTION:
        (sdists / f"{name}-0.1.0.tar.gz").write_bytes(name.encode())
    companions = tmp_path / "companions"
    companions.mkdir()
    (companions / "parallax_conformance-0.1.0-py3-none-any.whl").write_bytes(b"test support")
    return sdists, companions, tmp_path / "output"


def test_retained_source_inputs_build_without_checkout_fallback_and_keep_separate_validation(
    tmp_path: Path,
) -> None:
    sdists, companions, output = _inputs(tmp_path)
    commands: list[list[str]] = []

    def run(command: list[str], log: Path, environment: dict[str, str]) -> float:
        commands.append(command)
        assert "PYTHONPATH" not in environment
        if "wheel" in command:
            wheelhouse = Path(command[command.index("--wheel-dir") + 1])
            for name in source.PRODUCTION:
                (wheelhouse / f"{name}-0.1.0-py3-none-any.whl").write_bytes(name.encode())
        else:
            assert (
                str(output / "wheelhouse" / "parallax_postgres-0.1.0-py3-none-any.whl") in command
            )
            assert str(output / "companions") in command
        return 4.5

    with patch.object(source, "run_logged", run):
        source.build_and_validate(sdists, companions, output, "18.6")
    build, validation = commands
    assert {str(path) for path in sdists.glob("*.tar.gz")}.issubset(build)
    assert {"--no-cache-dir", "--no-deps", "-I"}.issubset(build)
    assert validation[2].endswith("validate_wheel.py")
    record = json.loads((output / "source.json").read_text())
    assert record["status"] == "passed"
    assert record["sdists"] == source.identities(list(sdists.glob("*.tar.gz")))
    assert len(record["wheels"]) == 6
    assert (
        output / "companions" / "parallax_conformance-0.1.0-py3-none-any.whl"
    ).read_bytes() == b"test support"


def test_incomplete_source_set_retains_failure_record_before_building(tmp_path: Path) -> None:
    sdists, companions, output = _inputs(tmp_path)
    next(sdists.glob("*.tar.gz")).unlink()
    with pytest.raises(ValueError, match="exactly the six production"):
        source.build_and_validate(sdists, companions, output, "18.6")
    assert json.loads((output / "source.json").read_text())["status"] == "failed"
