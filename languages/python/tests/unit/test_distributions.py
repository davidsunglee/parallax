from __future__ import annotations

import subprocess
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

import pytest

from tests._support import distributions


def _builder(calls: list[str]) -> Any:
    def build(command: list[str], **_options: object) -> None:
        package = command[command.index("--package") + 1]
        calls.append(package)
        out = Path(command[command.index("--out-dir") + 1])
        (out / f"{package.replace('-', '_')}-0.1.0-py3-none-any.whl").touch()

    return build


def test_workers_share_one_complete_build_but_invocations_build_fresh(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[str] = []
    monkeypatch.setattr(distributions.subprocess, "run", _builder(calls))
    directory = tmp_path / "first"
    with ThreadPoolExecutor(max_workers=2) as workers:
        outputs = list(workers.map(distributions.build_wheelhouse, [directory, directory]))
    assert outputs[0] == outputs[1]
    assert sorted(calls) == sorted(distributions.ALL_PACKAGES)
    assert all(wheel.is_file() for wheel in outputs[0].wheels.values())
    other = distributions.build_wheelhouse(tmp_path / "second")
    assert other.directory != outputs[0].directory
    assert sorted(calls) == sorted(distributions.ALL_PACKAGES * 2)


def test_a_failed_build_is_not_published_and_can_be_retried(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    directory = tmp_path / "wheelhouse"

    def fail(command: list[str], **_options: object) -> None:
        raise subprocess.CalledProcessError(1, command)

    monkeypatch.setattr(distributions.subprocess, "run", fail)
    with pytest.raises(subprocess.CalledProcessError):
        distributions.build_wheelhouse(directory)
    assert not directory.exists()
    assert not list(tmp_path.glob("wheelhouse-build-*"))
    calls: list[str] = []
    monkeypatch.setattr(distributions.subprocess, "run", _builder(calls))
    built = distributions.build_wheelhouse(directory)
    assert set(built.wheels) == set(distributions.ALL_PACKAGES)
