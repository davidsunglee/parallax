"""Build repaired adapter wheels and validate their exact bytes on native runners."""

from __future__ import annotations

import argparse
import json
import os
import platform
import shutil
import subprocess
import sys
import time
import tomllib
import urllib.request
from contextlib import ExitStack
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from interpreter_matrix import supported_minors
from wheel_postgres import provision

PY_ROOT = Path(__file__).resolve().parents[1]
REPO = PY_ROOT.parents[1]
TARGETS = Path(__file__).with_name("wheel_targets.json")
PYTHONS = supported_minors()
CIBUILDWHEEL = "4.3.5"


def targets() -> list[dict[str, str]]:
    return json.loads(TARGETS.read_text())


def matrix() -> list[dict[str, str]]:
    metadata = tomllib.loads((PY_ROOT / "packages/parallax-postgres/pyproject.toml").read_text())
    # The declared floor and the selected CPython minors must move together.
    floor = metadata["project"]["requires-python"]
    if floor != f">={PYTHONS[0]}":
        raise ValueError(f"review wheel Python selection for requires-python {floor!r}")
    return [{**target, "python": minor} for target in targets() for minor in PYTHONS]


def newest_postgres() -> str:
    with urllib.request.urlopen("https://www.postgresql.org/versions.json", timeout=60) as response:
        versions = json.load(response)
    entry = next(version for version in versions if str(version["major"]) == "18")
    minor = int(entry["latestMinor"])
    if minor < 6:
        raise ValueError("PostgreSQL 18 discovery is older than the required floor")
    return f"18.{minor}"


def _run(command: list[str], log: Path, env: dict[str, str] | None = None) -> None:
    print(subprocess.list2cmdline(command), flush=True)
    with log.open("a", encoding="utf-8") as output:
        output.write(subprocess.list2cmdline(command) + "\n")
        output.flush()
        subprocess.run(command, cwd=REPO, env=env, stdout=output, stderr=output, check=True)


def _native(target: dict[str, str], python: str) -> None:
    expected_platform = {"linux": "Linux", "macos": "Darwin", "windows": "Windows"}
    if platform.system() != expected_platform[target["platform"]]:
        raise ValueError(f"wrong platform: {platform.system()}")
    if platform.machine().lower() != target["arch"].lower():
        raise ValueError(f"native {target['arch']} runner required, got {platform.machine()}")
    if f"{sys.version_info.major}.{sys.version_info.minor}" != python:
        raise ValueError(f"host Python must be {python}, got {sys.version}")


def _companions(output: Path, env: dict[str, str]) -> None:
    for package in sorted((PY_ROOT / "packages").iterdir()):
        if package.name == "parallax-postgres":
            continue
        _run(
            [
                "uv",
                "build",
                "--project",
                str(PY_ROOT),
                "--wheel",
                "--package",
                package.name,
                "--python",
                sys.executable,
                "--out-dir",
                str(output / "companions"),
            ],
            output / "setup.log",
            env,
        )


def _build(target: dict[str, str], python: str, output: Path, env: dict[str, str]) -> None:
    identifier = f"cp{python.replace('.', '')}-{target['build']}"
    build_env = {
        **env,
        "CIBW_BUILD": identifier,
        "CIBW_ARCHS": target["arch"],
        "CIBW_BUILD_VERBOSITY": "1",
        "CIBW_ENABLE": "cpython-prerelease",
    }
    if target["platform"] == "linux":
        policy = "MUSLLINUX" if target["build"].startswith("musllinux") else "MANYLINUX"
        build_env[f"CIBW_{policy}_{target['arch'].upper()}_IMAGE"] = target["image"]
    _run(
        [
            sys.executable,
            "-m",
            "cibuildwheel",
            str(PY_ROOT / "packages/parallax-postgres"),
            "--output-dir",
            str(output / "wheelhouse"),
        ],
        output / "build.log",
        build_env,
    )
    wheels = list((output / "wheelhouse").glob("*.whl"))
    if len(wheels) != 1:
        raise ValueError(f"expected one repaired {identifier} wheel, got {wheels}")


def _linux_container(
    target: dict[str, str],
    output: Path,
    env: dict[str, str],
    postgres_version: str,
    lifetime: ExitStack,
) -> str:
    container = subprocess.check_output(
        [
            "docker",
            "run",
            "--detach",
            "--network",
            "host",
            "-v",
            f"{REPO}:/project",
            "-e",
            f"PARALLAX_WHEEL_DSN={env['PARALLAX_WHEEL_DSN']}",
            target["image"],
            "sleep",
            "infinity",
        ],
        env=env,
        text=True,
    ).strip()
    lifetime.callback(_run, ["docker", "rm", "--force", container], output / "setup.log", env)
    _run(
        [
            "docker",
            "exec",
            container,
            "sh",
            "/project/languages/python/tools/build_wheel_libpq.sh",
            postgres_version,
        ],
        output / "libpq-setup.log",
        env,
    )
    inspection = subprocess.check_output(["docker", "inspect", container], env=env, text=True)
    (output / "validation-container.json").write_text(inspection)
    return container


def _validate(
    target: dict[str, str],
    python: str,
    output: Path,
    env: dict[str, str],
    postgres_version: str,
    container: str | None,
) -> None:
    wheel = next((output / "wheelhouse").glob("*.whl"))
    validator = PY_ROOT / "tools/validate_wheel.py"
    arguments = [
        "--wheel",
        str(wheel),
        "--companions",
        str(output / "companions"),
        "--output",
        str(output / "validation"),
        "--postgres-version",
        postgres_version,
    ]
    if target["platform"] != "linux":
        _run([sys.executable, str(validator), *arguments], output / "validation.log", env)
        return
    interpreter = f"/opt/python/cp{python.replace('.', '')}-cp{python.replace('.', '')}/bin/python"
    # Use the same policy image as the build so a musl wheel cannot be tested
    # accidentally in the host's glibc environment. Docker has no emulation setup.
    translated = [
        str(Path("/project") / Path(arg).relative_to(REPO)) if arg.startswith(str(REPO)) else arg
        for arg in arguments
    ]
    if container is None:
        raise ValueError("Linux validation container was not provisioned")
    _run(
        [
            "docker",
            "exec",
            container,
            "sh",
            "-c",
            "export PATH=/opt/wheel-libpq/bin:$PATH; "
            'export LD_LIBRARY_PATH=/opt/wheel-libpq/lib:${LD_LIBRARY_PATH:-}; exec "$@"',
            "sh",
            interpreter,
            "/project/languages/python/tools/validate_wheel.py",
            *translated,
        ],
        output / "validation.log",
        env,
    )


def build(
    target_id: str, python: str, output: Path, postgres_version: str, companions: Path | None = None
) -> None:
    target = next(target for target in targets() if target["id"] == target_id)
    _native(target, python)
    output.mkdir(parents=True, exist_ok=False)
    record: dict[str, Any] = {
        "target": target_id,
        "python": python,
        "platform": platform.platform(),
        "arch": platform.machine(),
        "runner_arch": os.environ.get("RUNNER_ARCH"),
        "source_sha": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=REPO, text=True
        ).strip(),
        "run_id": os.environ.get("GITHUB_RUN_ID", "local"),
        "run_attempt": os.environ.get("GITHUB_RUN_ATTEMPT", "1"),
        "postgres_version": postgres_version,
        "status": "failed",
        "timings": {},
        "started_at": datetime.now(UTC).isoformat(),
        "cibuildwheel": CIBUILDWHEEL,
    }
    start = time.monotonic()
    try:
        _run(
            [sys.executable, "-m", "pip", "install", f"cibuildwheel=={CIBUILDWHEEL}"],
            output / "setup.log",
        )
        with ExitStack() as lifetime:
            postgres = lifetime.enter_context(provision(postgres_version, output / "postgres"))
            env = {**os.environ, **postgres.env}
            if companions is None:
                _companions(output, env)
            else:
                shutil.copytree(companions, output / "companions")
            container = (
                _linux_container(target, output, env, postgres_version, lifetime)
                if target["platform"] == "linux"
                else None
            )
            record["postgres"] = postgres.observations
            record["timings"]["setup_seconds"] = time.monotonic() - start
            started = time.monotonic()
            try:
                _build(target, python, output, env)
            finally:
                record["timings"]["build_repair_seconds"] = time.monotonic() - started
            _validate(target, python, output, env, postgres_version, container)
            record["status"] = "passed"
    except BaseException as error:
        record["status"] = "failed"
        record["error"] = f"{type(error).__name__}: {error}"
        raise
    finally:
        record["timings"]["total_seconds"] = time.monotonic() - start
        record["completed_at"] = datetime.now(UTC).isoformat()
        (output / "target.json").write_text(json.dumps(record, indent=2) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--matrix", action="store_true")
    parser.add_argument("--newest-postgres", action="store_true")
    parser.add_argument("--prepare-companions", type=Path)
    parser.add_argument("--companions", type=Path)
    parser.add_argument("--target", choices=[target["id"] for target in targets()])
    parser.add_argument("--python", choices=PYTHONS)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--postgres-version")
    args = parser.parse_args()
    if args.matrix:
        print(json.dumps({"include": matrix()}))
    elif args.newest_postgres:
        print(newest_postgres())
    elif args.prepare_companions:
        args.prepare_companions.mkdir(parents=True, exist_ok=False)
        _companions(args.prepare_companions.resolve(), dict(os.environ))
    elif all((args.target, args.python, args.output, args.postgres_version)):
        build(
            args.target, args.python, args.output.resolve(), args.postgres_version, args.companions
        )
    else:
        parser.error("build requires --target, --python, --output and --postgres-version")


if __name__ == "__main__":
    main()
