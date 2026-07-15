"""Generate (and check) the import-linter forbidden-edge complement.

Parallax enforces the module dependency DAG in Python with import-linter
``forbidden`` contracts. Rather than hand-maintain them, this tool derives them
from the single source of truth — the fenced ``dependency-graph`` block in
``core/spec/modules.md`` — plus the declared support-scope edges from the
``spec/python.md`` §7 table, computes each production scope's transitive
dependency closure, and emits the *complement*: every production scope pair the
closure does not permit becomes a forbidden import. This rejects illegal
non-edges, not merely wrong-direction edges (a ``layers`` contract cannot).

The core conformance-family exception (``modules.md``) is encoded structurally:
conformance scopes (``parallax.conformance.*``) are exempt on the *importing*
side (they may harness any behavioural scope), while every production scope is
forbidden from importing any conformance scope.

Usage
-----
* ``python tools/check_dag_sync.py``            verify committed contracts (default)
* ``python tools/check_dag_sync.py --check``    verify committed contracts (explicit)
* ``python tools/check_dag_sync.py --write``    regenerate the contracts in place

Default mode verifies and exits non-zero on any drift, so the same command backs
both the local gate and CI.
"""

from __future__ import annotations

import argparse
import re
import sys
from collections import deque
from collections.abc import Iterable, Mapping
from pathlib import Path

_TOOL = "tools/check_dag_sync.py"
_HERE = Path(__file__).resolve()
_PY_ROOT = _HERE.parents[1]
_REPO_ROOT = _HERE.parents[3]
MODULES_MD = _REPO_ROOT / "core" / "spec" / "modules.md"
PYPROJECT = _PY_ROOT / "pyproject.toml"

_BEGIN = "# >>> check_dag_sync.py: BEGIN GENERATED IMPORT-LINTER CONTRACTS >>>"
_END = "# <<< check_dag_sync.py: END GENERATED IMPORT-LINTER CONTRACTS <<<"

# Behavioural / support module tag -> Python enforcement scope (spec/python.md §7).
# `m-api-conformance` maps to the pytest-bounded `tests.api_conformance` and is
# enforced by the pytest collection boundary, not import-linter, so it is absent.
MODULE_SCOPE: Mapping[str, str] = {
    "m-core": "parallax.core.base",
    "m-descriptor": "parallax.core.descriptor",
    "m-pk-gen": "parallax.core.pk_gen",
    "m-inheritance": "parallax.core.inheritance",
    "m-value-object": "parallax.core.value_object",
    "m-op-algebra": "parallax.core.op_algebra",
    "m-sql": "parallax.core.sql_gen",
    "m-dialect": "parallax.core.dialect",
    "m-db-port": "parallax.core.db_port",
    "m-db-error": "parallax.core.db_error",
    "m-unit-work": "parallax.core.unit_work",
    "m-read-lock": "parallax.core.read_lock",
    "m-auto-retry": "parallax.core.auto_retry",
    "m-opt-lock": "parallax.core.opt_lock",
    "m-temporal-read": "parallax.core.temporal_read",
    "m-audit-write": "parallax.core.audit_write",
    "m-bitemp-write": "parallax.core.bitemp_write",
    "m-batch-write": "parallax.core.batch_write",
    "m-navigate": "parallax.core.navigate",
    "m-deep-fetch": "parallax.core.deep_fetch",
    "m-snapshot-read": "parallax.snapshot.materialize",
    "m-case-format": "parallax.conformance.case_format",
    "m-conformance-adapter": "parallax.conformance.cli",
}

# Support scopes carry no module tag in modules.md; their permitted direct
# dependencies come from the spec/python.md §7 table.
SUPPORT_SCOPE_DEPS: Mapping[str, frozenset[str]] = {
    "parallax.core.entity": frozenset(
        {
            "parallax.core.descriptor",
            "parallax.core.op_algebra",
            "parallax.core.temporal_read",
        }
    ),
    "parallax.snapshot.handle": frozenset(
        {
            "parallax.snapshot.materialize",
            "parallax.core.unit_work",
            "parallax.core.auto_retry",
            "parallax.core.read_lock",
            "parallax.core.opt_lock",
            "parallax.core.batch_write",
            "parallax.core.audit_write",
            "parallax.core.bitemp_write",
            "parallax.core.pk_gen",
            "parallax.core.sql_gen",
            "parallax.core.db_port",
            "parallax.core.entity",
        }
    ),
    "parallax.postgres": frozenset(
        {
            "parallax.core.db_port",
            "parallax.core.db_error",
            "parallax.core.dialect",
        }
    ),
}

# The conformance-family enforcement scopes that carry a module tag and thus
# appear as nodes in the DAG (m-case-format, m-conformance-adapter). They are
# exempt on the *importing* side: no forbidden contract is sourced from them.
CONFORMANCE_SCOPES: frozenset[str] = frozenset(
    {"parallax.conformance.case_format", "parallax.conformance.cli"}
)

# Every production scope is forbidden from importing *any* conformance scope
# (python.md §7). Rather than enumerate the conformance subtree — which silently
# leaves a newly added conformance module (`.adapter`, `.claim`, `.api_suite`, …)
# importable — the whole package is forbidden as one edge; import-linter treats a
# package forbidden module as covering all its descendants (`as_packages`).
CONFORMANCE_ROOT: str = "parallax.conformance"

ROOT_PACKAGES: tuple[str, ...] = (
    "parallax.conformance",
    "parallax.core",
    "parallax.postgres",
    "parallax.snapshot",
)


def parse_dependency_graph(text: str) -> list[tuple[str, str]]:
    """Extract ``A --> B`` edges from the fenced ``dependency-graph`` block."""
    match = re.search(r"```dependency-graph\n(.*?)\n```", text, re.DOTALL)
    if match is None:
        raise ValueError("no fenced ```dependency-graph``` block found in modules.md")
    edges: list[tuple[str, str]] = []
    for line in match.group(1).splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        edge = re.fullmatch(r"(\S+)\s*-->\s*(\S+)", stripped)
        if edge is None:
            raise ValueError(f"unparseable dependency-graph line: {line!r}")
        edges.append((edge.group(1), edge.group(2)))
    return edges


def build_adjacency(edges: Iterable[tuple[str, str]]) -> dict[str, frozenset[str]]:
    """Map every scope to the set of scopes it may *directly* depend on.

    Fails loudly rather than silently dropping a dependency: if a mapped module
    (one in ``MODULE_SCOPE``) depends on a core-DAG module that ``MODULE_SCOPE``
    does not model, the §7 enforcement map is stale and generation aborts. Edges
    whose *importer* is unmapped (a deferred / out-of-slice module the Python
    target does not enforce) are skipped. Support-scope dependency targets are
    likewise checked against the known scope set.
    """
    nodes = set(MODULE_SCOPE.values()) | set(SUPPORT_SCOPE_DEPS)
    for scope, deps in SUPPORT_SCOPE_DEPS.items():
        unknown = deps - nodes
        if unknown:
            raise ValueError(
                f"support scope {scope!r} depends on scopes absent from the §7 "
                f"enforcement map: {sorted(unknown)}"
            )
    direct: dict[str, set[str]] = {node: set() for node in nodes}
    for importer, imported in edges:
        if importer not in MODULE_SCOPE:
            continue
        if imported not in MODULE_SCOPE:
            raise ValueError(
                f"mapped module {importer!r} depends on {imported!r}, which "
                "MODULE_SCOPE does not model — the §7 enforcement map is stale"
            )
        direct[MODULE_SCOPE[importer]].add(MODULE_SCOPE[imported])
    for scope, deps in SUPPORT_SCOPE_DEPS.items():
        direct[scope].update(deps)
    return {node: frozenset(deps) for node, deps in direct.items()}


def transitive_closure(adjacency: Mapping[str, frozenset[str]], start: str) -> frozenset[str]:
    """All scopes reachable from ``start`` following permitted dependency edges."""
    seen: set[str] = set()
    queue: deque[str] = deque(adjacency.get(start, frozenset()))
    while queue:
        node = queue.popleft()
        if node in seen:
            continue
        seen.add(node)
        queue.extend(adjacency.get(node, frozenset()))
    return frozenset(seen)


def compute_forbidden(adjacency: Mapping[str, frozenset[str]]) -> dict[str, list[str]]:
    """For each production source scope, the sorted scopes it may not import.

    Targets are every *production* scope the scope's transitive closure does not
    reach, plus the whole ``parallax.conformance`` subtree as a single package
    edge — so every production scope is forbidden from importing any conformance
    scope, modelled or not.
    """
    production_sources = sorted(node for node in adjacency if node not in CONFORMANCE_SCOPES)
    production_targets = set(adjacency) - CONFORMANCE_SCOPES
    all_targets = production_targets | {CONFORMANCE_ROOT}
    forbidden: dict[str, list[str]] = {}
    for scope in production_sources:
        allowed = transitive_closure(adjacency, scope)
        blocked = all_targets - allowed - {scope}
        forbidden[scope] = sorted(blocked)
    return forbidden


def _toml_str_list(values: Iterable[str], indent: str = "    ") -> str:
    items = list(values)
    if not items:
        return "[]"
    body = "".join(f'{indent}"{value}",\n' for value in items)
    return f"[\n{body}]"


def render_block(forbidden: Mapping[str, list[str]]) -> str:
    """Render the ``[tool.importlinter]`` section (contracts sorted by scope)."""
    lines: list[str] = [
        f"# Generated by {_TOOL} from core/spec/modules.md — do not edit by hand.",
        f"# Regenerate with: uv run python {_TOOL} --write",
        "[tool.importlinter]",
        f"root_packages = {_toml_str_list(ROOT_PACKAGES)}",
    ]
    for scope in sorted(forbidden):
        blocked = forbidden[scope]
        lines.append("")
        lines.append("[[tool.importlinter.contracts]]")
        lines.append(f'name = "{scope} may import only its permitted dependencies"')
        lines.append('type = "forbidden"')
        lines.append(f'source_modules = ["{scope}"]')
        lines.append(f"forbidden_modules = {_toml_str_list(blocked)}")
    return "\n".join(lines)


def splice(current: str, block: str) -> str:
    """Replace the region between the generated markers with ``block``."""
    begin = current.find(_BEGIN)
    end = current.find(_END)
    if begin == -1 or end == -1 or end < begin:
        raise ValueError(f"generated-contract markers not found (or out of order) in {PYPROJECT}")
    before = current[: begin + len(_BEGIN)]
    after = current[end:]
    return f"{before}\n{block}\n{after}"


def generate() -> str:
    edges = parse_dependency_graph(MODULES_MD.read_text())
    adjacency = build_adjacency(edges)
    forbidden = compute_forbidden(adjacency)
    return render_block(forbidden)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "--check",
        action="store_true",
        help="verify the committed contracts match modules.md (default)",
    )
    group.add_argument(
        "--write",
        action="store_true",
        help="regenerate the contracts in pyproject.toml",
    )
    args = parser.parse_args(argv)

    block = generate()
    current = PYPROJECT.read_text()
    expected = splice(current, block)

    if args.write:
        if expected != current:
            PYPROJECT.write_text(expected)
            print(f"{_TOOL}: wrote regenerated import-linter contracts to {PYPROJECT}")
        else:
            print(f"{_TOOL}: import-linter contracts already up to date")
        return 0

    if expected != current:
        print(
            f"{_TOOL}: import-linter contracts are out of sync with core/spec/modules.md.\n"
            f"  Run `uv run python {_TOOL} --write` and commit the result.",
            file=sys.stderr,
        )
        return 1
    print(f"{_TOOL}: import-linter contracts are in sync with core/spec/modules.md")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
