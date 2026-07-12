"""Shared fixtures for the Parallax Python workspace test suites."""

from __future__ import annotations

import json
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

PY_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = PY_ROOT.parents[1]


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
