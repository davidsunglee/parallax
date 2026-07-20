"""Generate (and check) the import-linter forbidden-edge complement.

Parallax enforces the module dependency DAG in Python with import-linter
``forbidden`` contracts. Rather than hand-maintain them, this tool derives them
from the single source of truth — the fenced ``dependency-graph`` block in
``core/spec/modules.md`` — plus the declared support-scope edges from the
``spec/python.md`` §7 table, computes each production scope's transitive
dependency closure, and emits the *complement*: every production scope pair the
closure does not permit becomes a forbidden import. This rejects illegal
non-edges, not merely wrong-direction edges (a ``layers`` contract cannot).

Support-scope edges carry no module tag, so §7 is their only declaration, and
§7 states them **twice** — once in the prose table's "Allowed direct
dependencies" column and once in the fenced ``support-scope-graph`` block —
requiring that "the prose rows and the block MUST agree". All three
representations are therefore parity-checked against each other on every run:
the §7 prose rows, the §7 fence, and :data:`SUPPORT_SCOPE_DEPS`. Editing any one
of them alone fails generation, and so does editing two of them consistently
while the third disagrees.

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
PYTHON_MD = _PY_ROOT / "spec" / "python.md"
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

# The write-lowering child cluster (`_family`, `_write_types`, `_keyed_sql`,
# `_write_lowering`) is enforced as ONE group: the four modules share this grant
# row rather than each declaring its own. Grouping is deliberate — the cluster's
# internal homes move (COR-42 Phase 3 re-homed `_MARKER_KEYS` to keep the
# `_keyed_sql -> _write_lowering` back-edge from existing), and a per-module row
# would turn every such internal move into a spec edit. The group boundary is
# what carries the enforcement value: none of the four may reach the read side
# (`m-snapshot-read`, `m-deep-fetch`, `m-navigate`, `parallax.core.entity`).
_LOWERING_GROUP_DEPS: frozenset[str] = frozenset(
    {
        "parallax.core.base",
        "parallax.core.descriptor",
        "parallax.core.inheritance",
        "parallax.core.dialect",
        "parallax.core.db_port",
        "parallax.core.sql_gen",
        "parallax.core.unit_work",
        "parallax.core.opt_lock",
        "parallax.core.audit_write",
        "parallax.core.bitemp_write",
    }
)

# Support scopes carry no module tag in modules.md; their permitted direct
# dependencies come from the spec/python.md §7 table. Both of that section's
# representations — the prose rows and the fenced `support-scope-graph` block —
# are read back and compared against this table by
# :func:`check_support_scope_parity`.
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
            "parallax.core.sql_gen",
            "parallax.core.navigate",
            "parallax.core.db_port",
            "parallax.core.entity",
        }
    ),
    "parallax.snapshot.handle._wrap": frozenset(
        {
            "parallax.snapshot.materialize",
            "parallax.core.entity",
            "parallax.core.descriptor",
            "parallax.core.inheritance",
            "parallax.core.temporal_read",
        }
    ),
    "parallax.snapshot.handle._family": _LOWERING_GROUP_DEPS,
    "parallax.snapshot.handle._write_types": _LOWERING_GROUP_DEPS,
    "parallax.snapshot.handle._keyed_sql": _LOWERING_GROUP_DEPS,
    "parallax.snapshot.handle._write_lowering": _LOWERING_GROUP_DEPS,
    "parallax.postgres": frozenset(
        {
            "parallax.core.db_port",
            "parallax.core.db_error",
            "parallax.core.dialect",
        }
    ),
}

# Enforcement scopes nested inside another scope, mapped to that parent. The
# relation is declared rather than derived from dotted-path prefixes so that two
# independent consumers must agree about it:
#
# * this generator emits a child only as a contract *source*. Naming a child in
#   its own parent's ``forbidden_modules`` would overlap the parent's source
#   package, which import-linter >= 2.12 silently skips — the contract would
#   look present and enforce nothing.
# * ``tools/check_scope_ownership.py`` allows a production file to resolve to
#   more than one scope only along a chain declared here. A nested scope added
#   to :data:`SUPPORT_SCOPE_DEPS` but not registered here therefore fails the
#   ownership check instead of silently producing that skipped contract.
CHILD_SCOPE_PARENT: Mapping[str, str] = {
    "parallax.snapshot.handle._wrap": "parallax.snapshot.handle",
    "parallax.snapshot.handle._family": "parallax.snapshot.handle",
    "parallax.snapshot.handle._write_types": "parallax.snapshot.handle",
    "parallax.snapshot.handle._keyed_sql": "parallax.snapshot.handle",
    "parallax.snapshot.handle._write_lowering": "parallax.snapshot.handle",
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


_EDGE = re.compile(r"(\S+)\s*-->\s*(\S+)")


def _parse_edge_fence(text: str, fence: str, source: str) -> list[tuple[str, str]]:
    """Extract the ``A --> B`` edges from the fenced ``fence`` block in ``text``.

    The single owner of the fence grammar. ``dependency-graph`` (module tags,
    from ``modules.md``) and ``support-scope-graph`` (enforcement scopes, from
    ``spec/python.md`` §7) are the same notation over different vocabularies,
    so they differ only in fence name and in how the caller shapes the result.
    """
    match = re.search(rf"```{re.escape(fence)}\n(.*?)\n```", text, re.DOTALL)
    if match is None:
        raise ValueError(f"no fenced ```{fence}``` block found in {source}")
    edges: list[tuple[str, str]] = []
    for line in match.group(1).splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        edge = _EDGE.fullmatch(stripped)
        if edge is None:
            raise ValueError(f"unparseable {fence} line: {line!r}")
        edges.append((edge.group(1), edge.group(2)))
    return edges


def parse_dependency_graph(text: str) -> list[tuple[str, str]]:
    """Extract ``A --> B`` edges from the fenced ``dependency-graph`` block."""
    return _parse_edge_fence(text, "dependency-graph", "modules.md")


def parse_support_scope_graph(text: str) -> dict[str, frozenset[str]]:
    """Extract the declared support-scope edges from ``spec/python.md`` §7.

    Same ``A --> B`` grammar as the ``dependency-graph`` fence, but both sides
    name Python enforcement scopes rather than module tags, because support
    scopes carry no tag in ``modules.md``.
    """
    declared: dict[str, set[str]] = {}
    for importer, imported in _parse_edge_fence(text, "support-scope-graph", "spec/python.md"):
        declared.setdefault(importer, set()).add(imported)
    return {scope: frozenset(deps) for scope, deps in declared.items()}


# The §7 prose table. `_TABLE_HEADER` opens it; contiguous `|`-prefixed lines
# are its rows. A support-scope row is marked by "(support" in its first cell —
# behavioural rows carry an `m-…` module tag there instead and take their edges
# from `modules.md`, not from §7.
_TABLE_HEADER = "| Behavioral/support module |"
_SUPPORT_ROW = "(support"
_APPLICATION_OWNED = "(application-owned)"
_BACKTICKED = re.compile(r"`([^`]+)`")


def _table_rows(text: str) -> list[list[str]]:
    """The §7 enforcement-topology table as cell lists, separator row dropped."""
    lines = text.splitlines()
    header = next((i for i, line in enumerate(lines) if line.startswith(_TABLE_HEADER)), None)
    if header is None:
        raise ValueError("no §7 enforcement-topology table found in spec/python.md")
    rows: list[list[str]] = []
    for line in lines[header + 1 :]:
        if not line.startswith("|"):
            break
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if all(set(cell) <= set("-: ") for cell in cells):
            continue
        if len(cells) != 5:
            raise ValueError(f"§7 table row does not have 5 cells: {line!r}")
        rows.append(cells)
    if not rows:
        raise ValueError("§7 enforcement-topology table has no rows")
    return rows


def _row_scopes(scope_cell: str, owner_cell: str) -> list[str]:
    """The enforcement scopes a §7 row declares.

    Normally the "Enforcement scope" cell names them. The write-lowering child
    group states "those four scopes, sharing one grant row" there and enumerates
    them in the "Source owner/path" cell instead, so a scope cell naming none
    falls back to the owner cell. Within a cell, a backticked token starting
    with a dot (``._write_types``) abbreviates a sibling of the preceding full
    name and is expanded against it.
    """
    for cell in (scope_cell, owner_cell):
        names: list[str] = []
        for token in _BACKTICKED.findall(cell):
            if token.startswith("."):
                if not names:
                    raise ValueError(f"abbreviated §7 scope {token!r} has no preceding full name")
                names.append(f"{names[-1].rsplit('.', 1)[0]}{token}")
            elif token.startswith("parallax."):
                names.append(token)
        if names:
            return names
    raise ValueError(f"§7 support row names no enforcement scope: {scope_cell!r}")


def _row_grants(cell: str, scope: str) -> frozenset[str]:
    """The scopes a §7 row's "Allowed direct dependencies" cell grants.

    Only backticked tokens declare a grant: a module tag resolved through
    :data:`MODULE_SCOPE`, or a ``parallax.*`` scope named outright. Unbackticked
    prose in that cell names no enforcement scope (``psycopg`` is a third-party
    distribution, not a scope) and is not a grant. A backticked token that is
    neither shape is a spec error rather than something to skip quietly.
    """
    grants: set[str] = set()
    for token in _BACKTICKED.findall(cell):
        if token.startswith("parallax."):
            grants.add(token)
        elif token.startswith("m-"):
            mapped = MODULE_SCOPE.get(token)
            if mapped is None:
                raise ValueError(
                    f"§7 prose row for {scope!r} grants module tag {token!r}, which "
                    "MODULE_SCOPE does not model"
                )
            grants.add(mapped)
        else:
            raise ValueError(
                f"§7 prose row for {scope!r} grants {token!r}, which is neither a "
                "module tag nor a `parallax.*` enforcement scope"
            )
    return frozenset(grants)


def parse_support_scope_table(text: str) -> dict[str, frozenset[str]]:
    """Extract the declared support-scope edges from ``spec/python.md`` §7's prose rows.

    §7 states support-scope grants twice and requires the two to agree, so the
    prose rows are a first-class input rather than commentary on the fence. The
    composition-root row is the one support row that declares no enforcement
    scope — it is application-owned code, outside every scope — and is skipped
    by that exact marker, not by shape.
    """
    declared: dict[str, frozenset[str]] = {}
    for module, owner, scope_cell, deps_cell, _rule in _table_rows(text):
        if _SUPPORT_ROW not in module:
            continue
        if scope_cell == _APPLICATION_OWNED:
            continue
        scopes = _row_scopes(scope_cell, owner)
        grants = _row_grants(deps_cell, scopes[0])
        for scope in scopes:
            declared[scope] = grants
    return declared


def _compare_declarations(
    left_name: str,
    left: Mapping[str, frozenset[str]],
    right_name: str,
    right: Mapping[str, frozenset[str]],
    subject: str,
) -> None:
    """Fail when two declarations of the support-scope graph disagree."""
    left_only = sorted(set(left) - set(right))
    right_only = sorted(set(right) - set(left))
    if left_only or right_only:
        raise ValueError(
            f"{subject}: declared only in {left_name} {left_only}, "
            f"declared only in {right_name} {right_only}"
        )
    for scope in sorted(left):
        if left[scope] != right[scope]:
            raise ValueError(
                f"support scope {scope!r} has drifted between {left_name} and "
                f"{right_name}: {left_name} grants {sorted(left[scope])}, "
                f"{right_name} grants {sorted(right[scope])}"
            )


def check_support_scope_parity(
    declared: Mapping[str, frozenset[str]],
    prose: Mapping[str, frozenset[str]],
) -> None:
    """Fail when §7's prose rows, §7's fence, and :data:`SUPPORT_SCOPE_DEPS` disagree.

    Three declarations of one graph, so two comparisons. §7 itself requires
    that "the prose rows and the block MUST agree", so that arm runs first and
    reports a spec-internal inconsistency; only then is the spec compared
    against the tool's table, spec-relative, because the spec is authoritative.
    Checking both arms is what makes editing any single representation — or two
    of the three consistently — fail rather than pass.
    """
    _compare_declarations(
        "the spec/python.md §7 prose table",
        prose,
        "the spec/python.md §7 support-scope-graph block",
        declared,
        "spec/python.md §7 is internally inconsistent: its prose rows and its "
        "support-scope-graph block declare different support scopes",
    )
    _compare_declarations(
        "the spec",
        declared,
        "the tool",
        SUPPORT_SCOPE_DEPS,
        "SUPPORT_SCOPE_DEPS has drifted from the spec/python.md §7 support-scope-graph block",
    )


def check_child_scopes() -> None:
    """Fail when a declared child scope is not nested under its declared parent."""
    for child, parent in CHILD_SCOPE_PARENT.items():
        if parent not in SUPPORT_SCOPE_DEPS and parent not in MODULE_SCOPE.values():
            raise ValueError(f"child scope {child!r} names an undeclared parent scope {parent!r}")
        if not child.startswith(f"{parent}."):
            raise ValueError(f"child scope {child!r} is not nested inside its parent {parent!r}")


def scope_ancestors(scope: str) -> frozenset[str]:
    """Every declared scope that contains ``scope``, following the child chain."""
    seen: set[str] = set()
    current = CHILD_SCOPE_PARENT.get(scope)
    while current is not None and current not in seen:
        seen.add(current)
        current = CHILD_SCOPE_PARENT.get(current)
    return frozenset(seen)


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

    Child scopes (:data:`CHILD_SCOPE_PARENT`) are sources only, never targets.
    import-linter's ``forbidden`` contracts are package-scoped on both sides, so
    a child named inside its own parent's forbidden row overlaps that contract's
    source package and is silently skipped; and naming a child in some *other*
    scope's row would only restate what the parent's own entry already forbids
    for every descendant. For the same overlap reason a child's own row omits
    its ancestors.
    """
    production_sources = sorted(node for node in adjacency if node not in CONFORMANCE_SCOPES)
    production_targets = set(adjacency) - CONFORMANCE_SCOPES - set(CHILD_SCOPE_PARENT)
    all_targets = production_targets | {CONFORMANCE_ROOT}
    forbidden: dict[str, list[str]] = {}
    for scope in production_sources:
        allowed = transitive_closure(adjacency, scope)
        blocked = all_targets - allowed - {scope} - scope_ancestors(scope)
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
        f"# Generated by {_TOOL} from core/spec/modules.md and spec/python.md §7"
        " — do not edit by hand.",
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
    python_md = PYTHON_MD.read_text()
    check_support_scope_parity(
        parse_support_scope_graph(python_md), parse_support_scope_table(python_md)
    )
    check_child_scopes()
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
            f"{_TOOL}: import-linter contracts are out of sync with core/spec/modules.md"
            " and spec/python.md §7.\n"
            f"  Run `uv run python {_TOOL} --write` and commit the result.",
            file=sys.stderr,
        )
        return 1
    print(
        f"{_TOOL}: import-linter contracts are in sync with core/spec/modules.md"
        " and spec/python.md §7"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
