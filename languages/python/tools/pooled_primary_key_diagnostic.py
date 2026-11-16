"""Capture one pooled primary-key diagnostic suite into an output directory.

Each suite is a focused test that grades its readings in every ordinary run and
writes them when this launcher names an output directory. The launcher runs it
in a fresh pytest process with nothing beside it, then records beside the
readings what they were taken on: interpreter, platform, dependency lock,
commit, and a digest of the diagnostic sources. It opens no connection and
starts no server — a database suite reaches its database through the test
fixture, which this launcher requires rather than lets skip.

Readings are diagnostics, not retained evidence: keep them outside Git.

    uv run --frozen --python 3.15 python tools/pooled_primary_key_diagnostic.py \\
        --suite live --mode assigned --out /tmp/<capture>/live-before
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import subprocess
import sys
import time
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Final

WORKSPACE: Final = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(WORKSPACE))
# `sys.path` gains the workspace above, so this import cannot precede it.
from tests._support.pooled_key_diagnostic import (  # noqa: E402
    MODE_VARIABLE,
    MODES,
    OUT_VARIABLE,
)


@dataclass(frozen=True, slots=True)
class Suite:
    target: str
    """The pytest node or module the suite runs."""
    database: bool
    sources: tuple[str, ...]
    """What the readings were taken through, besides the target itself."""


_SHARED: Final = (
    "tools/pooled_primary_key_diagnostic.py",
    "tests/_support/pooled_key_diagnostic.py",
)
_INSTRUMENTS: Final = ("tests/unit/memory_instruments.py",)

SUITES: Final[dict[str, Suite]] = {
    "live": Suite(
        "tests/api/test_pooled_primary_key_diagnostic.py"
        "::test_every_frozen_case_tallies_and_stores_only_its_inserts",
        database=True,
        sources=(*_SHARED, "tests/api/_pooled_primary_key_diagnostic_support.py"),
    ),
    "provider": Suite(
        "tests/provider_contract/test_postgres_pool_contract.py"
        "::test_a_root_holds_its_pools_threads_and_sessions_only_until_it_closes",
        database=True,
        sources=_SHARED,
    ),
    "allocator-memory": Suite(
        "tests/unit/core/_execution/test_key_allocation_memory.py",
        database=False,
        sources=(*_SHARED, *_INSTRUMENTS),
    ),
    "pool-memory": Suite(
        "tests/unit/postgres/test_postgres_pool_memory.py",
        database=False,
        sources=(*_SHARED, *_INSTRUMENTS),
    ),
}


def prepared_output(out: Path) -> Path:
    """Create the empty output directory ``out``, refusing one whose parent is
    missing or that already holds a capture."""
    if not out.parent.is_dir():
        raise SystemExit(f"the output parent {out.parent} does not exist")
    if out.exists() and any(out.iterdir()):
        raise SystemExit(f"{out} already holds a capture")
    out.mkdir(exist_ok=True)
    return out


def command(suite: Suite) -> list[str]:
    return [sys.executable, "-m", "pytest", suite.target, "-p", "no:cacheprovider", "-q"]


def environment(suite: Suite, mode: str, out: Path) -> dict[str, str]:
    required = {"PARALLAX_REQUIRE_DB": "1"} if suite.database else {}
    return os.environ | required | {OUT_VARIABLE: str(out), MODE_VARIABLE: mode}


def _git(*arguments: str) -> str:
    return subprocess.run(
        ["git", *arguments], cwd=WORKSPACE, capture_output=True, text=True, check=True
    ).stdout.strip("\n")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def provenance(suite: Suite, name: str, mode: str, argv: Sequence[str]) -> dict[str, object]:
    sources = sorted({suite.target.split("::")[0], *suite.sources})
    digest = hashlib.sha256()
    for source in sources:
        digest.update(source.encode())
        digest.update(_sha256(WORKSPACE / source).encode())
    return {
        "suite": name,
        "mode": mode,
        "command": ["tools/pooled_primary_key_diagnostic.py", *argv],
        "pytest": command(suite)[1:],
        "python": {
            "version": sys.version,
            "implementation": platform.python_implementation(),
            "executable": sys.executable,
        },
        "platform": {
            "system": platform.platform(),
            "machine": platform.machine(),
        },
        "lockSha256": _sha256(WORKSPACE / "uv.lock"),
        "commit": _git("rev-parse", "HEAD"),
        "uncommitted": _git("status", "--porcelain", "--", ".").splitlines(),
        "diagnosticSources": sources,
        "diagnosticSourcesSha256": digest.hexdigest(),
    }


def main(argv: Sequence[str]) -> int:
    parser = argparse.ArgumentParser(
        description="Capture one pooled primary-key diagnostic suite into an output directory."
    )
    parser.add_argument("--suite", choices=sorted(SUITES), default="live")
    parser.add_argument("--mode", choices=MODES, default="assigned")
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    suite = SUITES[args.suite]
    out = prepared_output(args.out.resolve())
    record = provenance(suite, args.suite, args.mode, argv)
    started = time.monotonic()
    completed = subprocess.run(
        command(suite), cwd=WORKSPACE, env=environment(suite, args.mode, out), check=False
    )
    record["elapsedSeconds"] = round(time.monotonic() - started, 3)
    record["exitStatus"] = completed.returncode
    record["cells"] = sorted(path.name for path in out.glob("*.json"))
    (out / "provenance.json").write_text(json.dumps(record, indent=2, sort_keys=True) + "\n")
    if completed.returncode == 0 and not record["cells"]:
        print(f"{args.suite} passed but wrote no readings into {out}", file=sys.stderr)
        return 1
    return completed.returncode


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
