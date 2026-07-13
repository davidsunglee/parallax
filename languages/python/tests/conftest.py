"""Shared fixtures for the Parallax Python workspace test suites."""

from __future__ import annotations

import json
import os
import re
import subprocess
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

import pytest

PY_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = PY_ROOT.parents[1]


def case_document(case: Any) -> dict[str, Any]:
    """A case's raw YAML document as a plain ``dict`` (test-side typed accessor)."""
    return cast("dict[str, Any]", dict(case.document))


# Database-backed checks skipped because Docker/Postgres was unavailable — printed
# in a final summary so a skip is never silent (spec §6); CI fails on any skip.
_DB_SKIPS: list[str] = []


def record_db_skip(reason: str) -> None:
    """Record a skipped database-backed check for the end-of-session summary."""
    if reason not in _DB_SKIPS:
        _DB_SKIPS.append(reason)


@pytest.fixture(scope="session")
def provisioner() -> Iterator[Any]:
    """A session-scoped self-managed Testcontainers Postgres (spec §6).

    Skips the database-backed lane with a reason (never silently) when Docker or
    the provider cannot be brought up; the ``python-database`` CI job fails on any
    such skip, so a green CI run has exercised every database-backed check.
    """
    try:
        from parallax.conformance.provision import Provisioner

        instance = Provisioner()
    except Exception as exc:
        reason = f"Testcontainers Postgres unavailable: {type(exc).__name__}: {exc}"
        record_db_skip(reason)
        pytest.skip(reason)
        return
    try:
        yield instance
    finally:
        instance.close()


def pytest_terminal_summary(terminalreporter: Any) -> None:
    """Print the database-backed skip summary (silent skips are forbidden, §6)."""
    if not _DB_SKIPS:
        return
    terminalreporter.write_sep("=", "database-backed checks skipped")
    for reason in _DB_SKIPS:
        terminalreporter.write_line(f"SKIPPED (database): {reason}")
    if os.environ.get("PARALLAX_REQUIRE_DB") == "1":
        terminalreporter.write_line(
            "PARALLAX_REQUIRE_DB=1 set: skipped database checks are a failure"
        )
        raise pytest.UsageError("database-backed checks were skipped but required")


def adapter_schema() -> dict[str, Any]:
    """The conformance-adapter JSON Schema (the adapter wire contract)."""
    schema_path = REPO_ROOT / "core" / "schemas" / "conformance-adapter.schema.json"
    return json.loads(schema_path.read_text(encoding="utf-8"))


def canonical_snapshot_claim() -> dict[str, Any]:
    """The canonical ``slice-snapshot-1`` describe claim from ``slices.md``."""
    text = (REPO_ROOT / "core" / "spec" / "slices.md").read_text(encoding="utf-8")
    section = text.split("## Snapshot Conformance Slice", 1)[1]
    match = re.search(r"```json\n(.*?)\n```", section, re.DOTALL)
    assert match is not None, "no fenced json claim under the Snapshot Conformance Slice heading"
    return json.loads(match.group(1))


# Production distributions first, then the dev-only conformance tooling.
PRODUCTION_PACKAGES: tuple[str, ...] = (
    "parallax-core",
    "parallax-snapshot",
    "parallax-postgres",
)
ALL_PACKAGES: tuple[str, ...] = (*PRODUCTION_PACKAGES, "parallax-conformance")


@dataclass(frozen=True)
class Wheelhouse:
    """A directory of freshly built wheels plus a package-name -> wheel map."""

    directory: Path
    wheels: dict[str, Path]


@pytest.fixture(scope="session")
def wheelhouse(tmp_path_factory: pytest.TempPathFactory) -> Wheelhouse:
    """Build every distribution wheel once per session into a temp directory."""
    out = tmp_path_factory.mktemp("wheelhouse")
    for package in ALL_PACKAGES:
        subprocess.run(
            ["uv", "build", "--package", package, "--wheel", "--out-dir", str(out)],
            cwd=PY_ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
    wheels: dict[str, Path] = {}
    for package in ALL_PACKAGES:
        dist = package.replace("-", "_")
        matches = sorted(out.glob(f"{dist}-*.whl"))
        assert matches, f"no wheel built for {package}"
        wheels[package] = matches[-1]
    return Wheelhouse(directory=out, wheels=wheels)
