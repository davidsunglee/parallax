"""Fail when a Python source file exists on disk but not in git.

The changed-line coverage gate (``diff-cover coverage.xml --compare-branch
origin/main --fail-under 100``) derives its line inventory from **git**, not from
the filesystem. A production module that has never been ``git add``-ed therefore
contributes no changed lines: coverage.xml measures it (``source_pkgs =
["parallax"]`` follows imports, not the index), but diff-cover sees no diff for
it and silently omits it from the ratio. The gate then reports "100% diff-cover"
over whatever *was* tracked — a vacuous pass. This was observed during COR-42
Phase 2, where a new 448-line ``handle/_read.py`` was scored as 11 tracked lines
at 100%; staging it revealed the real 163 changed lines.

The test tree has the mirror-image failure. Tests are not measured
(``source_pkgs`` names only ``parallax``), but pytest collects from the
filesystem, so an untracked test file *does* run and *does* produce the coverage
that lets the gate pass — while being absent from the commit and therefore from
CI. Both directions let a phase claim coverage it has not committed, so both
roots are guarded.

``tools/`` is deliberately not guarded: ``python-static`` invokes each tool by
path, so an untracked gate fails loudly in CI on its own.

Usage
-----
* ``python tools/check_untracked_sources.py``          check (default)
* ``python tools/check_untracked_sources.py --check``  check (explicit)

Same ``--check``/exit-1 contract as ``tools/check_dag_sync.py``: it never
mutates anything, exits non-zero on any finding, and so backs both the local
gate and CI.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path, PurePosixPath

_TOOL = "tools/check_untracked_sources.py"
_HERE = Path(__file__).resolve()
PY_ROOT = _HERE.parents[1]

# git pathspecs (relative to PY_ROOT) handed to `git ls-files`. Kept coarse; the
# precise per-root shape is decided by the classifiers below so the rules stay
# readable and directly unit-testable.
PATHSPECS: tuple[str, ...] = ("packages", "tests")

PRODUCTION_LABEL = "production source (packages/*/src)"
TEST_LABEL = "test source (tests/)"


def is_production_source(relative_path: str) -> bool:
    """True for ``packages/<dist>/src/**/*.py`` — the roots coverage measures."""
    if not relative_path.endswith(".py"):
        return False
    parts = PurePosixPath(relative_path).parts
    return len(parts) > 3 and parts[0] == "packages" and parts[2] == "src"


def is_test_source(relative_path: str) -> bool:
    """True for ``tests/**/*.py`` — the roots pytest collects from disk."""
    if not relative_path.endswith(".py"):
        return False
    parts = PurePosixPath(relative_path).parts
    return len(parts) > 1 and parts[0] == "tests"


def untracked_paths(root: Path | None = None) -> list[str]:
    """Every path git does not track under :data:`PATHSPECS`, ignored or not.

    ``--exclude-standard`` is deliberately NOT passed. Being ignored on purpose
    does not make a file visible to diff-cover: a ``.gitignore``-d module under
    ``packages/*/src`` is still imported and still measured by ``coverage``
    (``source_pkgs = ["parallax"]`` follows imports, not the index), yet still
    contributes zero changed lines. That is the same vacuous pass an untracked
    file produces, so the guard must catch both to mean what it claims.

    The only ignore rule that can match a ``.py`` under the guarded roots is
    ``__pycache__/``, whose contents are ``.pyc`` and fall out at the extension
    check in :func:`is_production_source` / :func:`is_test_source`.

    Raises rather than returning empty when git is unavailable — a gate that
    cannot see the index must not report success.
    """
    workdir = PY_ROOT if root is None else root
    result = subprocess.run(
        ["git", "ls-files", "--others", "-z", "--", *PATHSPECS],
        cwd=workdir,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(f"`git ls-files` failed in {workdir}: {result.stderr.strip()}")
    return [line for line in result.stdout.split("\0") if line]


def classify(paths: list[str]) -> dict[str, list[str]]:
    """Group untracked paths by guarded root, dropping everything unguarded."""
    findings: dict[str, list[str]] = {PRODUCTION_LABEL: [], TEST_LABEL: []}
    for path in paths:
        if is_production_source(path):
            findings[PRODUCTION_LABEL].append(path)
        elif is_test_source(path):
            findings[TEST_LABEL].append(path)
    return {label: sorted(found) for label, found in findings.items() if found}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="verify no untracked Python sources exist under the guarded roots (default)",
    )
    parser.parse_args(argv)

    findings = classify(untracked_paths())
    if not findings:
        print(f"{_TOOL}: no untracked Python sources under {' or '.join(PATHSPECS)}")
        return 0

    print(
        f"{_TOOL}: untracked Python sources found. The changed-line coverage gate\n"
        "  compares against git, so these files are invisible to it and "
        "`diff-cover --fail-under 100`\n  can pass without ever scoring them.",
        file=sys.stderr,
    )
    for label in sorted(findings):
        print(f"  {label}:", file=sys.stderr)
        for path in findings[label]:
            print(f"    languages/python/{path}", file=sys.stderr)
    print(
        "  Run `git add` on each file (staging is enough) and re-run the gate.",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
