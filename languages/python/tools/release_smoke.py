"""Smoke-test all production distributions using hash-verified index downloads."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, TextIO

from release_artifacts import identity, verify

_PUBLIC_INDEX = "https://pypi.org/simple"
# The seeded installer evaluates tags for the actual clean-environment interpreter.
_SELECT = """
import json, sys
from pathlib import Path
from pip._vendor.packaging.tags import sys_tags
from pip._vendor.packaging.utils import parse_wheel_filename
compatible = {tag: rank for rank, tag in enumerate(sys_tags())}
selected = {}
for value in sys.argv[1:]:
    path = Path(value)
    project, version, build, tags = parse_wheel_filename(path.name)
    ranks = [compatible[tag] for tag in tags if tag in compatible]
    if ranks:
        candidate = (min(ranks), path.name, str(path))
        if project not in selected or candidate < selected[project]:
            selected[project] = candidate
print(json.dumps({project: candidate[2] for project, candidate in selected.items()}))
"""
_PROBE = """
import importlib, importlib.metadata, json, sys
from pathlib import Path
sys.path.insert(0, sys.argv[1])
from validate_wheel import installed_origins
version = sys.argv[2]
wheels = [Path(value) for value in sys.argv[3:]]
for wheel in wheels:
    name = wheel.name.split('-')[0]
    if importlib.metadata.version(name) != version:
        raise RuntimeError(f'{name} has an unexpected installed version')
    importlib.import_module(name.replace('_', '.', 1))
try:
    importlib.metadata.distribution('parallax-conformance')
except importlib.metadata.PackageNotFoundError:
    pass
else:
    raise RuntimeError('conformance was installed')
print(json.dumps(installed_origins(wheels), indent=2))
"""


def _environment() -> dict[str, str]:
    return {
        key: value
        for key, value in os.environ.items()
        if not key.startswith(("UV_", "PIP_"))
        and key not in {"PYTHONPATH", "PYTHONHOME", "VIRTUAL_ENV"}
    }


def selected_wheels(
    python: Path, manifest: dict[str, Any], downloaded: Path, environment: dict[str, str]
) -> list[Path]:
    candidates = [
        str(downloaded / record["filename"])
        for record in manifest["artifacts"]
        if record["kind"] == "wheel"
    ]
    selected = json.loads(
        subprocess.check_output(
            [str(python), "-I", "-c", _SELECT, *candidates], text=True, env=environment
        )
    )
    projects = {record["project"] for record in manifest["artifacts"]}
    if set(selected) != projects:
        raise ValueError("smoke requires one compatible downloaded wheel for each release project")
    if any(path not in candidates for path in selected.values()):
        raise ValueError("selected wheel is not from the verified index downloads")
    return [Path(selected[project]) for project in sorted(projects)]


def probe_installation(
    python: Path, wheels: list[Path], version: str, environment: dict[str, str], log: TextIO
) -> dict[str, str]:
    probe = subprocess.run(
        [
            str(python),
            "-I",
            "-c",
            _PROBE,
            str(Path(__file__).parent),
            version,
            *(str(path) for path in wheels),
        ],
        env=environment,
        text=True,
        capture_output=True,
    )
    log.write(probe.stdout)
    log.write(probe.stderr)
    probe.check_returncode()
    return json.loads(probe.stdout)


def smoke(bundle: Path, downloaded: Path, output: Path) -> None:
    manifest = verify(bundle)
    output.mkdir(parents=True, exist_ok=False)
    started = time.monotonic()
    result: dict[str, Any] = {
        "source_sha": manifest["source_sha"],
        "release_manifest": identity(bundle / "release-manifest.json"),
        "status": "failed",
    }
    try:
        for record in manifest["artifacts"]:
            if identity(downloaded / record["filename"])["sha256"] != record["sha256"]:
                raise ValueError("smoke inputs differ from verified release downloads")
        clean = _environment()
        with tempfile.TemporaryDirectory(prefix="parallax-release-smoke-") as temporary:
            directory = Path(temporary) / "venv"
            with (output / "install.log").open("w", encoding="utf-8") as stream:
                subprocess.run(
                    [
                        "uv",
                        "venv",
                        "--no-config",
                        "--seed",
                        "--default-index",
                        _PUBLIC_INDEX,
                        "--python",
                        sys.executable,
                        str(directory),
                    ],
                    check=True,
                    env=clean,
                    stdout=stream,
                    stderr=subprocess.STDOUT,
                )
                python = directory / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
                wheels = selected_wheels(python, manifest, downloaded, clean)
                subprocess.run(
                    [
                        "uv",
                        "pip",
                        "install",
                        "--no-config",
                        "--no-cache",
                        "--python",
                        str(python),
                        "--default-index",
                        _PUBLIC_INDEX,
                        *(str(path) for path in wheels),
                    ],
                    check=True,
                    env=clean,
                    stdout=stream,
                    stderr=subprocess.STDOUT,
                )
                origins = probe_installation(python, wheels, manifest["version"], clean, stream)
                (output / "origins.json").write_text(json.dumps(origins, indent=2) + "\n")
            result["wheels"] = [identity(path) for path in wheels]
            result["status"] = "passed"
    except BaseException as error:
        result["error"] = f"{type(error).__name__}: {error}"
        raise
    finally:
        result["elapsed_seconds"] = time.monotonic() - started
        (output / "smoke.json").write_text(json.dumps(result, indent=2) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--downloaded", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    smoke(args.bundle.resolve(), args.downloaded.resolve(), args.output.resolve())


if __name__ == "__main__":
    main()
