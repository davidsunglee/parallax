"""Child interpreters over every supported CPython minor, for the report tools.

A report that measures on every supported minor starts one child per reading:
the workspace's own interpreter for the current minor, and ``uv run`` against a
throwaway environment for any other. What the range is, how a child of either
kind is started, and what environment it measures in are decided here once so
every report answers the same matrix the same way.
"""

from __future__ import annotations

import os
import sys
import tempfile
import tomllib
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Final, cast

WORKSPACE: Final = Path(__file__).resolve().parents[1]
CURRENT_MINOR: Final = f"{sys.version_info.major}.{sys.version_info.minor}"
SUPPORTED_MINORS: Final = 2
HASH_SEED: Final = "0"

_COVERAGE_VARIABLES: Final = frozenset(
    {"COV_CORE_SOURCE", "COV_CORE_CONFIG", "COV_CORE_DATAFILE", "COVERAGE_PROCESS_START"}
)


def supported_minors() -> tuple[str, ...]:
    """Every CPython minor the workspace declares, oldest first.

    Read off the declared floor rather than the interpreter spawning the
    children, so a report run on the prior minor still names the latest one and a
    matrix short by a runtime cannot look complete.
    """
    declared = cast(
        "str",
        tomllib.loads((WORKSPACE / "pyproject.toml").read_text())["project"]["requires-python"],
    )
    floor = declared.removeprefix(">=").strip()
    parts = floor.split(".")
    if not (
        declared.startswith(">=") and len(parts) == 2 and all(part.isdigit() for part in parts)
    ):
        raise SystemExit(
            f"requires-python {declared!r} is not the bare '>=<major>.<minor>' "
            "floor the supported-minor matrix requires"
        )
    major, minor = (int(part) for part in parts)
    return tuple(f"{major}.{minor + above}" for above in range(SUPPORTED_MINORS))


def authority_minor(authority: Mapping[str, object]) -> str:
    """The CPython minor a Budget Contract's authority fingerprint names."""
    version = str(authority.get("cpython", ""))
    parts = version.split(".")
    if len(parts) < 2 or not (parts[0].isdigit() and parts[1].isdigit()):
        raise ValueError(f"authority cpython {version!r} does not name a <major>.<minor>")
    return f"{parts[0]}.{parts[1]}"


def child_environment(runtime: str, namespace: str) -> dict[str, str]:
    """The environment a ``runtime`` child measures in.

    A child of this interpreter's own minor inherits the import path that reached
    here; a child of another minor must not, because this environment's extension
    modules were built for another ABI, so its path is dropped and uv is pointed at
    a throwaway environment named by ``namespace``. Coverage is never inherited,
    and hashing is pinned so container sizes are the same in every child.
    """
    environment = {
        name: value for name, value in os.environ.items() if name not in _COVERAGE_VARIABLES
    }
    environment["PYTHONHASHSEED"] = HASH_SEED
    if runtime == CURRENT_MINOR:
        environment["PYTHONPATH"] = os.pathsep.join(entry for entry in sys.path if entry)
        return environment
    for name in ("PYTHONPATH", "PYTHONHOME", "VIRTUAL_ENV"):
        environment.pop(name, None)
    environment["UV_PROJECT_ENVIRONMENT"] = str(
        Path(tempfile.gettempdir()) / f"parallax-{namespace}-{runtime}"
    )
    return environment


def child_command(runtime: str, script: Path, arguments: Sequence[str]) -> list[str]:
    """What starts ``script`` with ``arguments`` on ``runtime``."""
    if runtime == CURRENT_MINOR:
        return [sys.executable, str(script), *arguments]
    return ["uv", "run", "--frozen", "--python", runtime, "python", str(script), *arguments]
