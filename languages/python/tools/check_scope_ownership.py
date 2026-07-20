"""Fail when a production Python file belongs to no enforcement scope.

``spec/python.md`` §7 maps every behavioral and support module onto a Python
enforcement scope, and ``tools/check_dag_sync.py`` turns those scopes into
import-linter ``forbidden`` contracts. Nothing proved the *converse*: that every
production source file actually falls inside one of them. A file outside every
scope is governed by no contract at all — it may import anything, and no gate
says so. That was not hypothetical. ``parallax/snapshot/wrap.py`` shipped as
production code owned by no scope until COR-42 retired it; a review-time
inventory found it, and only because someone went looking.

This walks the filesystem instead. Every ``packages/*/src/**/*.py`` file in the
production distributions must resolve to exactly one enforcement scope, or to an
exact, justified package-interface exemption. Three findings fail the check:

* **unowned** — the file matches no declared scope and is not exempt;
* **overlapping owners** — the file matches several scopes that are not a
  declared parent/child chain (:data:`check_dag_sync.CHILD_SCOPE_PARENT`).
  Nesting must be declared, because a nested scope the generator does not know
  about is emitted into its own parent's forbidden row, where import-linter
  silently skips it — a contract that looks present and enforces nothing;
* **stale exemption** — an exempt path that no longer exists, or that a scope
  now owns, so the exemption is carrying nothing.

The scope inventory is *imported* from ``check_dag_sync`` rather than restated,
so §7 stays declared exactly once. This check and
``tools/check_untracked_sources.py`` cover the same ``packages/*/src`` root and
are complementary rather than overlapping: ownership asks whether a file belongs
to a scope, trackedness asks whether git knows the file exists.

The conformance distribution is development-only (§8) and is skipped: its files
are excluded by dotted path under ``check_dag_sync.CONFORMANCE_ROOT`` rather
than by a hand-listed distribution name, so a newly added *production*
distribution is walked automatically.

Usage
-----
* ``python tools/check_scope_ownership.py``          check (default)
* ``python tools/check_scope_ownership.py --check``  check (explicit)

Same ``--check``/exit-1 contract as ``tools/check_dag_sync.py`` and
``tools/check_untracked_sources.py``: it never mutates anything, exits non-zero
on any finding, and so backs both the local gate and CI.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Mapping
from itertools import pairwise
from pathlib import Path

import check_dag_sync as dag

_TOOL = "tools/check_scope_ownership.py"
_HERE = Path(__file__).resolve()
PY_ROOT = _HERE.parents[1]
PACKAGES = PY_ROOT / "packages"

# Production files that no single scope can own, each with the reason it cannot.
# Keys are POSIX paths relative to `packages/`. An entry that stops being true —
# the file disappears, or a scope grows to cover it — is itself a finding.
EXEMPTIONS: Mapping[str, str] = {
    "parallax-core/src/parallax/core/__init__.py": (
        "distribution package interface: re-exports the §8 `parallax.core` developer "
        "surface across the descriptor, entity, op-algebra and temporal-read scopes, "
        "so no single scope owns it"
    ),
    "parallax-snapshot/src/parallax/snapshot/__init__.py": (
        "distribution package interface: re-exports the §8 `parallax.snapshot` surface "
        "(`connect`, `Snapshot`, `Execution`, the arity errors) from "
        "`parallax.snapshot.handle`, and sits above both snapshot scopes"
    ),
}


def declared_scopes() -> frozenset[str]:
    """Every enforcement scope §7 declares, as imported from ``check_dag_sync``."""
    return frozenset(dag.MODULE_SCOPE.values()) | frozenset(dag.SUPPORT_SCOPE_DEPS)


def module_path(relative_path: str) -> str:
    """Dotted module path for a ``<dist>/src/<pkg>/...`` file, ``__init__`` folded in."""
    parts = list(Path(relative_path).parts)[2:]
    if parts[-1] == "__init__.py":
        parts = parts[:-1]
    else:
        parts[-1] = parts[-1].removesuffix(".py")
    return ".".join(parts)


def owning_scopes(module: str, scopes: frozenset[str]) -> list[str]:
    """Declared scopes containing ``module``, outermost first."""
    owners = [s for s in scopes if module == s or module.startswith(f"{s}.")]
    return sorted(owners, key=len)


def is_declared_chain(owners: list[str], children: Mapping[str, str]) -> bool:
    """True when each owner after the first declares its predecessor as parent."""
    return all(children.get(deeper) == shallower for shallower, deeper in pairwise(owners))


def production_files() -> list[str]:
    """Every ``packages/*/src/**/*.py`` path outside the dev-only conformance tree."""
    found: list[str] = []
    for path in sorted(PACKAGES.glob("*/src/**/*.py")):
        relative = path.relative_to(PACKAGES).as_posix()
        if module_path(relative).startswith(f"{dag.CONFORMANCE_ROOT}."):
            continue
        if module_path(relative) == dag.CONFORMANCE_ROOT:
            continue
        found.append(relative)
    return found


def audit(
    paths: list[str],
    scopes: frozenset[str],
    children: Mapping[str, str],
    exemptions: Mapping[str, str],
) -> dict[str, list[str]]:
    """Group every ownership finding by kind; an empty result means the tree is clean."""
    unowned: list[str] = []
    overlapping: list[str] = []
    claimed_exemptions: list[str] = []
    for relative in paths:
        owners = owning_scopes(module_path(relative), scopes)
        if not owners:
            if relative not in exemptions:
                unowned.append(relative)
            continue
        if relative in exemptions:
            claimed_exemptions.append(f"{relative} (now owned by {owners[-1]})")
        if len(owners) > 1 and not is_declared_chain(owners, children):
            overlapping.append(f"{relative} (owned by {', '.join(owners)})")
    present = set(paths)
    missing = [f"{path} (no such file)" for path in exemptions if path not in present]
    stale = sorted(claimed_exemptions + missing)
    findings = {
        "production files owned by no enforcement scope": sorted(unowned),
        "production files owned by scopes with no declared nesting": sorted(overlapping),
        "exemptions that no longer describe the tree": stale,
    }
    return {label: found for label, found in findings.items() if found}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="verify every production source file has exactly one scope owner (default)",
    )
    parser.parse_args(argv)

    paths = production_files()
    findings = audit(paths, declared_scopes(), dag.CHILD_SCOPE_PARENT, EXEMPTIONS)
    if not findings:
        print(
            f"{_TOOL}: all {len(paths)} production source files resolve to one "
            f"enforcement scope or an exact exemption ({len(EXEMPTIONS)})"
        )
        return 0

    print(
        f"{_TOOL}: enforcement-scope ownership findings. A production file outside\n"
        "  every scope of spec/python.md §7 is covered by no import-linter contract,\n"
        "  so no gate constrains what it imports.",
        file=sys.stderr,
    )
    for label in sorted(findings):
        print(f"  {label}:", file=sys.stderr)
        for entry in findings[label]:
            print(f"    languages/python/packages/{entry}", file=sys.stderr)
    print(
        "  Declare the owning scope in spec/python.md §7 (and check_dag_sync.py), or\n"
        "  add an exact, justified exemption to EXEMPTIONS in this tool.",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
