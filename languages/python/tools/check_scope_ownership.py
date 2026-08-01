"""Fail when a production Python file belongs to no enforcement scope.

``spec/python.md`` §7 maps every behavioral and support module onto a Python
enforcement scope, and ``tools/check_dag_sync.py`` turns those scopes into
import-linter ``forbidden`` contracts. Neither proves the *converse*: that every
production source file actually falls inside one of them. A file outside every
scope is governed by no contract at all — it may import anything, and no other
gate reports it, so an unowned module silently bypasses dependency enforcement
entirely.

This walks the filesystem instead. Every ``packages/*/src/**/*.py`` file in the
production distributions must resolve to exactly one *most-specific*
enforcement scope — plus that scope's declared ancestors, if it has any — or to
an exact, justified package-interface exemption.

**A file matching two scopes is not by itself a finding.** Where §7 declares a
child scope over a private implementation module, every file inside it matches
both the child and the parent, and that is the point: the child's own grant row
is what governs it. What fails is overlap that *nobody declared*.

Four findings fail the check:

* **unowned** — the file matches no declared scope and is not exempt;
* **undeclared overlapping owners** — the file matches several scopes that do
  not form a parent/child chain declared in
  :data:`check_dag_sync.CHILD_SCOPE_PARENT`. Nesting must be declared, because a
  nested scope the generator does not know about is emitted into its own
  parent's forbidden row, where import-linter silently skips it — a contract
  that looks present and enforces nothing;
* **import-free module beside a zero-grant scope** — see below;
* **stale exemption** — an exempt path that no longer exists, or that a scope
  now owns, so the exemption is carrying nothing.

Zero-grant scopes
-----------------

A scope §7 grants nothing may import nothing, and its generated row says so by
forbidding every scope outside its own package plus its declared *sibling*
child scopes. Two module shapes are outside that row's reach: the shared parent
package, which a package-scoped ``forbidden`` row can never name from inside,
and a sibling module over which §7 declares no child scope. The second one is
reachable here, and it is only invisible when it imports nothing first-party:
importing a sibling that has first-party imports of its own breaks the row on
an indirect chain to whatever that sibling reaches. So the invariant that turns
the zero-grant row into a complete gate is that **every module inside such a
package either resolves to a scope the row can name or carries a first-party
import** — and that is a fact about files, which is why it is checked here and
not in ``check_dag_sync.py``, whose inputs are scopes.

The rule is derived from the scope tables (every declared child scope granted
nothing, and the package holding it), not written against one package; today it
selects ``parallax.snapshot.handle``, the only package with a zero-grant scope.
The parent package's own interface module is outside the rule because no scope
declaration could bring it inside a row that structurally cannot name its own
ancestor.

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
import ast
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
        "surface across the entity, op-algebra and temporal-read scopes, so no single "
        "scope owns it"
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


def first_party_imports(source: str) -> frozenset[str]:
    """Every first-party module an ``import`` statement in ``source`` names.

    First party is the distribution root ``check_dag_sync.ROOT_PACKAGES`` are
    spelled under, so the two tools agree on what import-linter treats as a
    first-party edge. A relative import is first-party whatever it resolves to
    and is recorded unresolved. Imports guarded by ``TYPE_CHECKING`` count:
    import-linter's graph contains them too.
    """
    roots = frozenset(root.split(".", 1)[0] for root in dag.ROOT_PACKAGES)

    def first_party(name: str) -> bool:
        return any(name == root or name.startswith(f"{root}.") for root in roots)

    found: set[str] = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            found.update(alias.name for alias in node.names if first_party(alias.name))
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                found.add("." * node.level + (node.module or ""))
            elif node.module is not None and first_party(node.module):
                found.add(node.module)
    return frozenset(found)


def zero_grant_scopes() -> Mapping[str, str]:
    """Declared child scopes §7 grants nothing, mapped to the package holding them."""
    return {
        scope: parent
        for scope, parent in dag.CHILD_SCOPE_PARENT.items()
        if scope in dag.SUPPORT_SCOPE_DEPS and not dag.SUPPORT_SCOPE_DEPS[scope]
    }


def modules_escaping_a_zero_grant_row(paths: list[str], scopes: frozenset[str]) -> list[str]:
    """Import-free modules a zero-grant scope's forbidden row cannot reach.

    Such a module is named by no contract and reaches nothing that is, so
    importing it from the zero-grant module would pass ``lint-imports``. Sibling
    modules that do carry first-party imports need no entry in the row: the
    import is caught on the chain through them.
    """
    found: set[str] = set()
    for scope, parent in zero_grant_scopes().items():
        nameable = dag.scope_siblings(scope) | {scope}
        for relative in paths:
            module = module_path(relative)
            if not module.startswith(f"{parent}."):
                continue
            owners = owning_scopes(module, scopes)
            if owners and owners[-1] in nameable:
                continue
            if first_party_imports((PACKAGES / relative).read_text()):
                continue
            found.add(f"{relative} (imports nothing first-party, and {scope} cannot name it)")
    return sorted(found)


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
    """Group every ownership finding by kind; an empty result means the tree is clean.

    A file with several owners is a finding only when they are not a declared
    chain: a file inside a declared child scope legitimately matches the child
    and every ancestor above it.

    Ownership alone does not settle a package holding a zero-grant scope, whose
    row is only complete while every module beside it is either nameable in that
    row or reachable through a first-party import, so that arm runs here too.
    """
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
        "import-free modules a zero-grant scope's contract cannot name": (
            modules_escaping_a_zero_grant_row(paths, scopes)
        ),
        "exemptions that no longer describe the tree": stale,
    }
    return {label: found for label, found in findings.items() if found}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="verify every production source file has one most-specific scope owner (default)",
    )
    parser.parse_args(argv)

    paths = production_files()
    scopes = declared_scopes()
    findings = audit(paths, scopes, dag.CHILD_SCOPE_PARENT, EXEMPTIONS)
    if not findings:
        nested = sum(1 for path in paths if len(owning_scopes(module_path(path), scopes)) > 1)
        print(
            f"{_TOOL}: all {len(paths)} production source files resolve to exactly one "
            f"most-specific enforcement scope (plus any declared ancestor scopes: "
            f"{nested} file(s) sit inside a declared child scope) or an exact "
            f"exemption ({len(EXEMPTIONS)}); beside a zero-grant scope, every module "
            f"is one its row can name or carries a first-party import"
        )
        return 0

    print(
        f"{_TOOL}: enforcement-scope ownership findings. A production file outside\n"
        "  every scope of spec/python.md §7 is covered by no import-linter contract,\n"
        "  so no gate constrains what it imports; a file under several scopes that\n"
        "  are not a declared parent/child chain has an enforcement model nothing\n"
        "  agrees on, and a child scope missing from CHILD_SCOPE_PARENT generates a\n"
        "  contract import-linter silently skips. An import-free module beside a\n"
        "  zero-grant scope is reached by neither that scope's forbidden row nor any\n"
        "  chain out of it, so the row would stop proving the scope imports nothing.",
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
