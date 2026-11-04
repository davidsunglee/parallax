"""Select changes that can affect wheel construction, loaders, or their proof."""

from __future__ import annotations

import argparse
import fnmatch
import subprocess
from collections.abc import Iterable
from pathlib import Path

from validate_wheel import TESTS

REPO = Path(__file__).resolve().parents[3]
INPUTS = (
    ".github/workflows/ci.yml",
    ".github/workflows/wheels.yml",
    ".github/workflows/wheel-refresh.yml",
    "languages/python/pyproject.toml",
    "languages/python/uv.lock",
    "languages/python/packages/*/pyproject.toml",
    "languages/python/packages/*/setup.py",
    "languages/python/packages/*/MANIFEST.in",
    "languages/python/packages/parallax-postgres/src/*",
    "languages/python/packages/parallax-core/src/parallax/core/base/*",
    "languages/python/packages/parallax-core/src/parallax/core/__init__.py",
    "languages/python/tests/conftest.py",
    "languages/python/tests/_support/*",
    "languages/python/tests/unit/tools/test_validate_wheel.py",
    "languages/python/tests/unit/tools/test_wheel*.py",
    "languages/python/tools/validate_wheel.py",
    "languages/python/tools/wheel*.py",
    "languages/python/tools/wheel_targets.json",
    "languages/python/tools/build_wheel_libpq.sh",
    "languages/python/tools/interpreter_matrix.py",
    "languages/python/tools/production_origins.py",
    "languages/python/tools/python_workspace.py",
    *(f"languages/python/{test}" for test in TESTS),
)


def relevant(paths: Iterable[str]) -> bool:
    return any(fnmatch.fnmatchcase(path, pattern) for path in paths for pattern in INPUTS)


def changed(base: str) -> bool:
    if (
        not base
        or subprocess.run(
            ["git", "cat-file", "-e", f"{base}^{{commit}}"],
            cwd=REPO,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        ).returncode
    ):
        return True
    paths = (
        subprocess.check_output(
            ["git", "diff", "--name-only", "--no-renames", "-z", base, "HEAD"], cwd=REPO
        )
        .decode(errors="surrogateescape")
        .split("\0")
    )
    return relevant(paths)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", required=True)
    args = parser.parse_args()
    print("true" if changed(args.base) else "false")


if __name__ == "__main__":
    main()
