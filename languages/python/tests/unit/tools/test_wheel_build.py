from __future__ import annotations

import os
import platform
import subprocess
from io import StringIO
from pathlib import Path
from urllib.error import URLError

import pytest
import yaml

import wheel_build


def _no_delay(seconds: float) -> None:
    assert seconds >= 0


def test_every_supported_runtime_has_the_complete_native_platform_matrix() -> None:
    cells = wheel_build.matrix()
    expected = {
        "manylinux2014-x86_64",
        "manylinux_2_28-aarch64",
        "musllinux-x86_64",
        "musllinux-aarch64",
        "macos-arm64",
        "macos-x86_64",
        "windows-amd64",
    }
    assert len(cells) == 14
    for runtime in ("3.14", "3.15"):
        assert {cell["id"] for cell in cells if cell["python"] == runtime} == expected
    arm_linux = [
        cell for cell in cells if cell["platform"] == "linux" and cell["arch"] == "aarch64"
    ]
    assert all(cell["runner"] == "ubuntu-24.04-arm" for cell in arm_linux)


def test_an_emulated_linux_arm_build_is_refused_before_building(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(platform, "system", lambda: "Linux")
    monkeypatch.setattr(platform, "machine", lambda: "x86_64")
    target = next(target for target in wheel_build.targets() if target["id"] == "musllinux-aarch64")
    with pytest.raises(ValueError, match="native aarch64 runner required"):
        wheel_build.build(target["id"], "3.15", tmp_path / "cell", "18.6")


def test_a_transient_release_feed_failure_retries_without_changing_the_selected_version(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    attempts: list[str] = []

    def response(url: str, *, timeout: int) -> StringIO:
        attempts.append(url)
        assert timeout > 0
        if len(attempts) == 1:
            raise URLError("temporary TLS timeout")
        return StringIO('[{"major": "18", "latestMinor": "6"}]')

    monkeypatch.setattr(wheel_build.urllib.request, "urlopen", response)
    monkeypatch.setattr(wheel_build.time, "sleep", _no_delay)
    assert wheel_build.newest_postgres() == "18.6"
    assert len(attempts) == 2


def test_a_persistent_release_feed_failure_never_supplies_a_fallback_version(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    attempts: list[str] = []

    def unavailable(url: str, *, timeout: int) -> StringIO:
        attempts.append(url)
        assert timeout > 0
        raise URLError("unavailable release feed")

    monkeypatch.setattr(wheel_build.urllib.request, "urlopen", unavailable)
    monkeypatch.setattr(wheel_build.time, "sleep", _no_delay)
    with pytest.raises(URLError, match="unavailable release feed"):
        wheel_build.newest_postgres()
    assert len(attempts) == 3


def test_workflow_preparation_stops_before_publishing_an_empty_postgres_version(
    tmp_path: Path,
) -> None:
    workflow = yaml.safe_load((wheel_build.REPO / ".github/workflows/wheels.yml").read_text())
    step = next(step for step in workflow["jobs"]["prepare"]["steps"] if step.get("id") == "matrix")
    python = tmp_path / "python"
    python.write_text(
        "#!/bin/sh\n"
        'case "$*" in\n'
        "  *--newest-postgres*) exit 23;;\n"
        "  *--matrix*) echo '{\"include\":[]}';;\n"
        "  *) exit 24;;\n"
        "esac\n"
    )
    python.chmod(0o755)
    output = tmp_path / "outputs"
    result = subprocess.run(
        ["bash", "-e", "-o", "pipefail", "-c", step["run"]],
        cwd=wheel_build.REPO,
        env={
            **os.environ,
            "PATH": f"{tmp_path}{os.pathsep}{os.environ['PATH']}",
            "GITHUB_OUTPUT": str(output),
        },
        capture_output=True,
    )
    assert result.returncode == 23
    assert not output.exists()
