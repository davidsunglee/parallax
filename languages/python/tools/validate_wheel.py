"""Validate exact adapter-wheel bytes under both supported psycopg implementations."""

from __future__ import annotations

import argparse
import email
import hashlib
import importlib
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import sysconfig
import time
import tomllib
import traceback
import venv
import xml.etree.ElementTree as ET
import zipfile
from collections.abc import Mapping, Sequence
from contextlib import ExitStack
from pathlib import Path
from typing import Any

PY_ROOT = Path(__file__).resolve().parents[1]
TESTS = (
    "tests/unit/postgres/test_postgres_compiled_loaders.py",
    "tests/provider_contract/test_postgres_compiled_loaders.py",
    "tests/provider_contract/test_postgres_timestamp_delivery.py",
    "tests/provider_contract/test_postgres_open_bound_bind.py",
)


def validation_dependencies() -> list[str]:
    with (PY_ROOT / "pyproject.toml").open("rb") as stream:
        configured = tomllib.load(stream)["dependency-groups"]["dev"]
    names = {"pytest", "filelock", "sqlglot"}
    return [
        requirement
        for requirement in configured
        if re.split(r"[<>=!~;\[]", requirement, maxsplit=1)[0] in names
    ]


def digest(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def driver_requirement(wheel: Path, driver: str) -> str:
    with zipfile.ZipFile(wheel) as archive:
        (metadata,) = [name for name in archive.namelist() if name.endswith(".dist-info/METADATA")]
        message = email.message_from_bytes(archive.read(metadata))
    for value in message.get_all("Requires-Dist", []):
        match = re.fullmatch(r"psycopg(?:\[[^]]+\])?([^;]+)", value)
        if match:
            return f"psycopg[{driver}]{match.group(1)}"
    raise RuntimeError("candidate wheel does not declare its psycopg constraint")


def run_logged(command: Sequence[str], log: Path, environment: Mapping[str, str]) -> float:
    started = time.monotonic()
    try:
        with log.open("w", encoding="utf-8") as stream:
            stream.write(json.dumps(list(command)) + "\n")
            stream.flush()
            subprocess.run(
                command,
                cwd=log.parent,
                env=environment,
                stdout=stream,
                stderr=subprocess.STDOUT,
                check=True,
            )
    finally:
        elapsed = time.monotonic() - started
        log.with_suffix(".seconds.json").write_text(
            json.dumps({"elapsed_seconds": elapsed}) + "\n", encoding="utf-8"
        )
    return elapsed


def test_counts(path: Path) -> dict[str, int]:
    cases = ET.parse(path).getroot().findall(".//testcase")
    counts = {
        key: sum(case.find(tag) is not None for case in cases)
        for key, tag in (("skipped", "skipped"), ("failed", "failure"), ("errors", "error"))
    }
    return {"passed": len(cases) - sum(counts.values()), **counts}


def _wheel_files(wheels: Sequence[Path]) -> dict[str, str]:
    expected: dict[str, str] = {}
    for wheel in wheels:
        with zipfile.ZipFile(wheel) as archive:
            expected.update(
                (name, hashlib.sha256(archive.read(name)).hexdigest())
                for name in archive.namelist()
                if name.startswith("parallax/") and not name.endswith("/")
            )
    return expected


def installed_origins(wheels: Sequence[Path]) -> dict[str, str]:
    expected = _wheel_files(wheels)
    site = Path(sysconfig.get_path("purelib")).resolve()
    for name, checksum in expected.items():
        installed = site / name
        if not installed.is_file() or digest(installed) != checksum:
            raise RuntimeError(f"installed file does not match supplied wheel: {name}")
    origins: dict[str, str] = {}
    for name, module in tuple(sys.modules.items()):
        if name != "parallax" and not name.startswith("parallax."):
            continue
        origin = getattr(module, "__file__", None)
        if origin is None:
            for location in getattr(module, "__path__", ()):
                if not Path(location).resolve().is_relative_to(site):
                    raise RuntimeError(f"namespace {name} escaped installed wheels: {location}")
            continue
        path = Path(origin).resolve()
        if not path.is_relative_to(site):
            raise RuntimeError(f"module {name} escaped installed wheels: {path}")
        relative = path.relative_to(site).as_posix()
        if expected.get(relative) != digest(path):
            raise RuntimeError(f"module {name} is not from supplied wheels: {path}")
        origins[name] = str(path)
    return origins


class _InstalledGuard:
    def __init__(self, wheels: Sequence[Path], output: Path) -> None:
        self.wheels = wheels
        self.output = output

    def pytest_sessionfinish(self, session: Any) -> None:
        try:
            origins = installed_origins(self.wheels)
            self.output.write_text(json.dumps(origins, indent=2) + "\n", encoding="utf-8")
        except Exception:
            session.exitstatus = 1
            traceback.print_exc()


def _exercise(args: argparse.Namespace) -> int:
    import psycopg
    import pytest

    importlib.import_module("parallax.postgres")

    if psycopg.pq.__impl__ != args.driver:
        raise RuntimeError(f"selected {psycopg.pq.__impl__!r}, expected {args.driver!r}")
    wheels = [args.wheel, *sorted(args.companions.glob("*.whl"))]
    for wheel in wheels:
        distribution = wheel.name.split("-", 1)[0]
        importlib.import_module(distribution.replace("_", ".", 1))
    installed_origins(wheels)
    observations = {
        "implementation": psycopg.pq.__impl__,
        "psycopg_version": psycopg.__version__,
        "libpq_version": psycopg.pq.version(),
        "python_version": platform.python_version(),
        "machine": platform.machine(),
        "platform": sysconfig.get_platform(),
    }
    (args.output / "driver.json").write_text(json.dumps(observations) + "\n", encoding="utf-8")
    refused = subprocess.run(
        [sys.executable, "-I", "-c", "import parallax.postgres"],
        env={**os.environ, "PSYCOPG_IMPL": "python"},
        capture_output=True,
        text=True,
    )
    (args.output / "pure-python-refusal.log").write_text(refused.stderr, encoding="utf-8")
    if refused.returncode == 0 or "running its 'python' implementation" not in refused.stderr:
        raise RuntimeError("adapter startup did not refuse psycopg's pure-Python implementation")
    sys.path.insert(0, str(PY_ROOT))
    return int(
        pytest.main(
            [
                *(str(PY_ROOT / test) for test in TESTS),
                "--rootdir",
                str(PY_ROOT),
                "-c",
                str(PY_ROOT / "pyproject.toml"),
                "--durations=0",
                f"--junitxml={args.output / 'tests.xml'}",
                f"--timing-report={args.output / 'timings'}",
            ],
            plugins=[_InstalledGuard(wheels, args.output / "origins.json")],
        )
    )


def _driver(args: argparse.Namespace, driver: str) -> dict[str, Any]:
    started = time.monotonic()
    result: dict[str, Any] = {"status": "failed"}
    output = args.output / driver
    output.mkdir(parents=True, exist_ok=True)
    environment = {
        key: value
        for key, value in os.environ.items()
        if key not in {"PYTHONPATH", "PYTHONHOME", "PYTEST_ADDOPTS", "VIRTUAL_ENV"}
    }
    environment.update(
        PSYCOPG_IMPL=driver,
        PARALLAX_REQUIRE_DB="1",
        PARALLAX_WHEEL_POSTGRES_VERSION=args.postgres_version,
        PYTEST_DISABLE_PLUGIN_AUTOLOAD="1",
    )
    try:
        directory = output / "venv"
        venv.EnvBuilder(with_pip=True, clear=True).create(directory)
        python = directory / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
        companions = sorted(args.companions.glob("*.whl"))
        if not companions:
            raise RuntimeError("no companion wheels supplied")
        requirement = driver_requirement(args.wheel, driver)
        result["install_seconds"] = run_logged(
            [
                str(python),
                "-I",
                "-m",
                "pip",
                "install",
                "--no-cache-dir",
                "--no-binary=psycopg-c",
                str(args.wheel),
                *(str(path) for path in companions),
                requirement,
                *validation_dependencies(),
            ],
            output / "install.log",
            environment,
        )
        if driver == "c":
            result["pg_config_version"] = subprocess.check_output(
                ["pg_config", "--version"], env=environment, text=True
            ).strip()
        result["test_seconds"] = run_logged(
            [
                str(python),
                "-I",
                str(Path(__file__).resolve()),
                "--wheel",
                str(args.wheel),
                "--companions",
                str(args.companions),
                "--output",
                str(output),
                "--postgres-version",
                args.postgres_version,
                "--driver",
                driver,
            ],
            output / "tests.log",
            environment,
        )
        result["tests"] = test_counts(output / "tests.xml")
        if result["tests"]["passed"] == 0 or any(
            result["tests"][key] for key in ("skipped", "failed", "errors")
        ):
            raise RuntimeError(f"required checks did not all pass: {result['tests']}")
        result.update(json.loads((output / "driver.json").read_text(encoding="utf-8")))
        result["origins_file"] = f"{driver}/origins.json"
        result["status"] = "passed"
    except Exception as failure:
        result["error"] = f"{type(failure).__name__}: {failure}"
        (output / "failure.log").write_text(traceback.format_exc(), encoding="utf-8")
        if (output / "tests.xml").exists():
            result["tests"] = test_counts(output / "tests.xml")
    finally:
        result["elapsed_seconds"] = time.monotonic() - started
        for stage, field in (("install", "install_seconds"), ("tests", "test_seconds")):
            timing = output / f"{stage}.seconds.json"
            if timing.exists():
                result[field] = json.loads(timing.read_text(encoding="utf-8"))["elapsed_seconds"]
        shutil.rmtree(output / "venv", ignore_errors=True)
    return result


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--wheel", required=True, type=Path)
    parser.add_argument("--companions", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--postgres-version", required=True)
    parser.add_argument("--driver", choices=("binary", "c"), help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    args.wheel = args.wheel.resolve(strict=True)
    args.companions = args.companions.resolve(strict=True)
    args.output = args.output.resolve()
    args.output.mkdir(parents=True, exist_ok=True)
    if args.driver is not None:
        with ExitStack() as libraries:
            if sys.platform == "win32":
                pg_config = shutil.which("pg_config")
                if pg_config is None:
                    raise RuntimeError("pg_config must identify the system libpq DLL directory")
                libraries.enter_context(os.add_dll_directory(str(Path(pg_config).resolve().parent)))
            return _exercise(args)
    result: dict[str, Any] = {
        "status": "failed",
        "wheel": {"filename": args.wheel.name, "sha256": digest(args.wheel)},
        "companions": [
            {"filename": path.name, "sha256": digest(path)}
            for path in sorted(args.companions.glob("*.whl"))
        ],
        "postgres_version": args.postgres_version,
        "drivers": {},
    }
    try:
        if (
            not re.fullmatch(r"18\.[0-9]+", args.postgres_version)
            or int(args.postgres_version.split(".")[1]) < 6
        ):
            raise RuntimeError("wheel validation requires selected PostgreSQL >=18.6,<19")
        if not os.environ.get("PARALLAX_WHEEL_DSN"):
            raise RuntimeError("PARALLAX_WHEEL_DSN must name a provisioned PostgreSQL server")
        for driver in ("binary", "c"):
            result["drivers"][driver] = _driver(args, driver)
        if all(driver["status"] == "passed" for driver in result["drivers"].values()):
            result["status"] = "passed"
    except Exception as failure:
        result["error"] = f"{type(failure).__name__}: {failure}"
    finally:
        (args.output / "validation.json").write_text(
            json.dumps(result, indent=2) + "\n", encoding="utf-8"
        )
    return 0 if result["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
