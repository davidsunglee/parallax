"""Audit every workspace distribution's dependency declarations.

Three parts run, every one of them even after another fails:

* **deptry**, once per workspace member from :func:`python_workspace.load_workspace`,
  against that member's ``pyproject.toml`` and ``src``. The virtual workspace root
  declares no distribution of its own and is never audited this way.
* ``check_distribution_dependencies``, which owns the ``parallax-*`` sibling
  declarations. The members share the PEP 420 ``parallax`` namespace, so deptry
  sees every sibling import as first-party and every declared sibling as unused;
  its DEP002 finding on a sibling is therefore ignored, for exactly the names
  the workspace members carry.
* ``check_dev_dependencies``, the development-dependency inventory.

The flags every member shares are stated here once rather than in each member
manifest.

Usage: ``uv run python tools/audit_dependencies.py`` (from ``languages/python``);
prints each part's findings and exits non-zero when any part fails.
"""

from __future__ import annotations

import os
import sys
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Final

import check_dev_dependencies
import check_distribution_dependencies
from python_workspace import NAMESPACE, Member, Workspace, load_workspace

PY_ROOT = Path(__file__).resolve().parents[1]

PACKAGE_MODULES: Final[Mapping[str, str]] = {
    "psycopg-pool": "psycopg_pool",
    "pyyaml": "yaml",
}

DeptryRunner = Callable[[Sequence[str]], int]
"""Runs deptry with the given command-line arguments; returns its exit status."""

NativeCheck = tuple[str, Callable[[], int]]

NATIVE_CHECKS: Final[tuple[NativeCheck, ...]] = (
    ("check_distribution_dependencies", check_distribution_dependencies.main),
    ("check_dev_dependencies", check_dev_dependencies.main),
)


def deptry_arguments(workspace: Workspace, member: Member) -> list[str]:
    siblings = "|".join(sorted(sibling.name for sibling in workspace.members))
    package_modules = ",".join(f"{name}={module}" for name, module in PACKAGE_MODULES.items())
    return [
        "--config",
        os.path.relpath(member.directory / "pyproject.toml"),
        "--known-first-party",
        NAMESPACE,
        "--package-module-name-map",
        package_modules,
        "--per-rule-ignores",
        f"DEP002={siblings}",
        os.path.relpath(member.directory / "src"),
    ]


def run_deptry(arguments: Sequence[str]) -> int:
    from deptry.cli import cli

    try:
        cli.main(args=list(arguments), prog_name="deptry")
    except SystemExit as exit_:
        return 1 if exit_.code else 0


def audit(
    workspace: Workspace,
    deptry: DeptryRunner,
    native_checks: Sequence[NativeCheck] = NATIVE_CHECKS,
) -> list[str]:
    """Run every part over ``workspace``; returns the name of each part that failed."""
    failed: list[str] = []
    for member in workspace.members:
        part = f"deptry {member.name}"
        print(f"== {part}", flush=True)
        if deptry(deptry_arguments(workspace, member)) != 0:
            failed.append(part)
    for part, check in native_checks:
        print(f"== {part}", flush=True)
        if check() != 0:
            failed.append(part)
    return failed


def main(argv: list[str] | None = None) -> int:
    del argv
    failed = audit(load_workspace(PY_ROOT), run_deptry)
    if failed:
        print(f"audit_dependencies: failed: {', '.join(failed)}", file=sys.stderr)
        return 1
    print("audit_dependencies: every part passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
