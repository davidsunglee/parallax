from __future__ import annotations

import base64
import csv
import hashlib
import io
import json
import os
import subprocess
import venv
import zipfile
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

import release_smoke as smoke


@pytest.fixture
def clean_python(tmp_path: Path) -> Path:
    directory = tmp_path / "clean"
    venv.EnvBuilder(with_pip=True).create(directory)
    return directory / ("Scripts/python.exe" if os.name == "nt" else "bin/python")


def _wheel(directory: Path, scope: str) -> Path:
    name = f"parallax_{scope}"
    info = f"{name}-0.1.0.dist-info"
    files = {
        f"parallax/{scope}/__init__.py": b"value = 42\n",
        f"{info}/METADATA": (
            f"Metadata-Version: 2.4\nName: parallax-{scope}\nVersion: 0.1.0\n"
        ).encode(),
        f"{info}/WHEEL": b"Wheel-Version: 1.0\nRoot-Is-Purelib: true\nTag: py3-none-any\n",
    }
    record = io.StringIO()
    writer = csv.writer(record)
    for name, data in files.items():
        digest = base64.urlsafe_b64encode(hashlib.sha256(data).digest()).rstrip(b"=").decode()
        writer.writerow([name, f"sha256={digest}", len(data)])
    writer.writerow([f"{info}/RECORD", "", ""])
    files[f"{info}/RECORD"] = record.getvalue().encode()
    path = directory / f"parallax_{scope}-0.1.0-py3-none-any.whl"
    with zipfile.ZipFile(path, "w") as archive:
        for name, data in files.items():
            archive.writestr(name, data)
    return path


def test_candidate_selection_and_probe_reject_substituted_installed_bytes(
    tmp_path: Path,
    clean_python: Path,
) -> None:
    wheels = [
        _wheel(tmp_path, scope)
        for scope in ("core", "descriptor", "snapshot", "postgres", "evolution", "aws")
    ]
    incompatible = tmp_path / "parallax_postgres-0.1.0-cp313-cp313-win32.whl"
    incompatible.touch()
    manifest = {
        "artifacts": [
            {
                "project": path.name.split("-")[0].replace("_", "-"),
                "filename": path.name,
                "kind": "wheel",
            }
            for path in [*wheels, incompatible]
        ]
    }
    selected = smoke.selected_wheels(clean_python, manifest, tmp_path, {})
    assert set(selected) == set(wheels)
    subprocess.run(
        [
            str(clean_python),
            "-I",
            "-m",
            "pip",
            "install",
            "--no-index",
            "--no-deps",
            *map(str, selected),
        ],
        check=True,
        capture_output=True,
    )
    log = io.StringIO()
    origins = smoke.probe_installation(clean_python, selected, "0.1.0", {}, log)
    Path(origins["parallax.core"]).write_text("value = 43\n")
    with pytest.raises(subprocess.CalledProcessError) as failure:
        smoke.probe_installation(clean_python, selected, "0.1.0", {}, log)
    assert "installed file does not match supplied wheel" in failure.value.stderr


def test_download_hash_mismatch_fails_before_installation(tmp_path: Path) -> None:
    bundle = tmp_path / "bundle"
    bundle.mkdir()
    (bundle / "release-manifest.json").write_text("{}")
    downloaded = tmp_path / "downloaded"
    downloaded.mkdir()
    path = downloaded / "candidate.whl"
    path.write_bytes(b"different bytes")
    manifest = {"source_sha": "a" * 40, "artifacts": [{"filename": path.name, "sha256": "0" * 64}]}
    with (
        patch.object(smoke, "verify", return_value=manifest),
        pytest.raises(ValueError, match="verified release downloads"),
    ):
        smoke.smoke(bundle, downloaded, tmp_path / "evidence")
    record = json.loads((tmp_path / "evidence" / "smoke.json").read_text())
    assert record["status"] == "failed"
    assert record["release_manifest"] == smoke.identity(bundle / "release-manifest.json")


def test_installation_uses_explicit_downloads_and_no_ambient_package_indexes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bundle = tmp_path / "bundle"
    bundle.mkdir()
    (bundle / "release-manifest.json").write_text("{}")
    downloaded = tmp_path / "downloaded"
    downloaded.mkdir()
    wheels = [
        _wheel(downloaded, scope)
        for scope in ("core", "descriptor", "snapshot", "postgres", "evolution", "aws")
    ]
    manifest = {
        "source_sha": "a" * 40,
        "version": "0.1.0",
        "artifacts": [smoke.identity(path) for path in wheels],
    }
    monkeypatch.setenv("UV_EXTRA_INDEX_URL", "https://unwanted.invalid/simple")
    monkeypatch.setenv("PIP_INDEX_URL", "https://unwanted.invalid/simple")
    commands: list[list[str]] = []

    def run(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        commands.append(command)
        assert not any(name.startswith(("PIP_", "UV_")) for name in kwargs["env"])
        return subprocess.CompletedProcess(command, 0, stdout="{}", stderr="")

    with (
        patch.object(smoke, "verify", return_value=manifest),
        patch.object(smoke, "selected_wheels", return_value=wheels),
        patch.object(smoke.subprocess, "run", run),
    ):
        smoke.smoke(bundle, downloaded, tmp_path / "evidence")
    install = commands[1]
    assert {str(path) for path in wheels}.issubset(install)
    assert "--find-links" not in install
    assert "--no-config" in install
    assert install[install.index("--default-index") + 1] == "https://pypi.org/simple"
    evidence = tmp_path / "evidence"
    assert not (evidence / "venv").exists()
    assert json.loads((evidence / "smoke.json").read_text())["status"] == "passed"
