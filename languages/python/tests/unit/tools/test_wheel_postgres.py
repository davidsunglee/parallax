from __future__ import annotations

import json
import subprocess
import sys
import threading
from collections.abc import Sequence
from pathlib import Path
from typing import Any, cast

import pytest

import wheel_postgres as postgres


def test_windows_download_selects_the_requested_version_and_architecture() -> None:
    page = """
        <span>Version <!-- -->18.6</span>
        <a href="https://sbp.enterprisedb.com/getfile.jsp?fileid=186">
          <img alt="Windows x86-64"></a>
        <a href="https://sbp.enterprisedb.com/getfile.jsp?fileid=other">
          <img alt="Linux x86-64"></a>
        <span>Version 17.11</span>
        <a href="https://sbp.enterprisedb.com/getfile.jsp?fileid=1711">
          <img alt="Windows x86-64"></a>
    """

    assert postgres.windows_download(page, "18.6").endswith("fileid=186")
    assert postgres.windows_download(page, "17.11").endswith("fileid=1711")
    with pytest.raises(ValueError, match="does not advertise"):
        postgres.windows_download(page, "18.7")


@pytest.mark.parametrize("version", ["18.5", "19.0", "18", "18.6rc1", "18.6;false"])
def test_an_unsupported_server_selection_fails_before_provisioning(
    tmp_path: Path, version: str
) -> None:
    with (
        pytest.raises(ValueError, match="outside the required"),
        postgres.provision(version, tmp_path),
    ):
        pytest.fail("unsupported version was provisioned")
    assert not (tmp_path / "setup.log").exists()


def _docker_commands(
    monkeypatch: pytest.MonkeyPatch, *, actual: str = "180006", cleanup_fails: bool = False
) -> list[list[str]]:
    invoked: list[list[str]] = []

    def run(arguments: Sequence[str], **options: Any) -> subprocess.CompletedProcess[str]:
        invoked.append(list(arguments))
        output = ""
        status = 0
        if arguments[:3] == ["docker", "image", "inspect"]:
            output = json.dumps(
                [
                    {
                        "Id": "sha256:local",
                        "RepoDigests": ["postgres@sha256:remote"],
                        "Architecture": "arm64",
                    }
                ]
            )
        elif arguments[:2] == ["docker", "run"]:
            output = "container-id\n"
        elif arguments[-1] == "show server_version_num":
            output = actual
        elif arguments[-1] == "show server_version":
            output = "18.6"
        elif arguments[:2] == ["docker", "logs"]:
            output = "database system is ready to accept connections"
        elif arguments[:2] == ["docker", "rm"] and cleanup_fails:
            status = 1
            output = "daemon refused removal"
        assert options["env"]
        options["stdout"].write(output)
        return subprocess.CompletedProcess(arguments, status)

    monkeypatch.setattr(postgres.sys, "platform", "linux")
    monkeypatch.setattr(postgres.subprocess, "run", run)
    return invoked


def test_docker_provisioning_records_native_image_and_exact_server_and_cleans_up(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    commands = _docker_commands(monkeypatch)

    with postgres.provision("18.6", tmp_path) as setup:
        assert setup.observations["image_architecture"] == "arm64"
        assert setup.observations["image_digests"] == ["postgres@sha256:remote"]
        assert setup.observations["server_version_num"] == 180006
        assert setup.env["PARALLAX_WHEEL_DSN"] == "postgresql://postgres@127.0.0.1:55432/postgres"

    assert ["docker", "pull", "postgres:18.6"] in commands
    assert [
        "docker",
        "exec",
        "container-id",
        "pg_isready",
        "-h",
        "127.0.0.1",
        "-U",
        "postgres",
    ] in commands
    assert commands[-1] == ["docker", "rm", "-f", "container-id"]
    assert "ready to accept" in (tmp_path / "server.log").read_text()
    assert "show server_version_num" in (tmp_path / "setup.log").read_text()


def test_an_incorrect_server_version_fails_and_retains_logs_before_cleanup(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    commands = _docker_commands(monkeypatch, actual="180005")

    with (
        pytest.raises(ValueError, match=r"expected exact 18\.6"),
        postgres.provision("18.6", tmp_path),
    ):
        pytest.fail("incorrect server was accepted")

    assert (tmp_path / "server.log").is_file()
    assert commands[-1] == ["docker", "rm", "-f", "container-id"]


def test_cleanup_failure_preserves_the_validation_failure(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _docker_commands(monkeypatch, cleanup_fails=True)

    with pytest.raises(ExceptionGroup) as caught, postgres.provision("18.6", tmp_path):
        raise RuntimeError("candidate validation failed")

    original, cleanup = caught.value.exceptions
    assert isinstance(original, RuntimeError)
    assert str(original) == "candidate validation failed"
    assert isinstance(cleanup, ExceptionGroup)
    assert isinstance(
        cast("ExceptionGroup[Exception]", cleanup).exceptions[0], subprocess.CalledProcessError
    )
    assert "daemon refused" in (tmp_path / "setup.log").read_text()


def test_command_capture_returns_while_the_server_descendant_keeps_stdout_open(
    tmp_path: Path,
) -> None:
    sentinel = tmp_path / "stop-server"
    descendant = (
        "from pathlib import Path\nimport time\n"
        f"while not Path({str(sentinel)!r}).exists():\n    time.sleep(0.01)\n"
    )
    start = (
        "import subprocess, sys\n"
        f"subprocess.Popen([sys.executable, '-c', {descendant!r}], close_fds=False)\n"
        "print('server started', flush=True)\n"
    )
    commands = postgres._Commands(tmp_path)  # pyright: ignore[reportPrivateUsage] - daemon output capture is this test's subject
    fallback_stop = threading.Timer(5, sentinel.touch)
    fallback_stop.start()
    try:
        assert commands.run([sys.executable, "-c", start]) == "server started"
        assert not sentinel.exists(), "capturing the command waited for its server descendant"
    finally:
        sentinel.touch()
        fallback_stop.cancel()
