"""Parse the normative module-dependency graph and assert it is a legal DAG.

Two modes:

* **DAG check** (default) — validate the graph in ``dependency-graph.md``::

      uv run python -m reference_harness.dep_graph_check core/spec/dependency-graph.md

* **Coverage gate** (``--coverage``) — the DAG check **plus** assert every
  in-scope module (MVP / fast-follow / definitely-do) has at least one
  compatibility fixture tagged to it::

      uv run python -m reference_harness.dep_graph_check --coverage core/spec core/compatibility

The machine-readable source of truth for the graph is the fenced
```` ```dependency-graph ```` block in ``dependency-graph.md``. Each line is an
edge ``A --> B`` meaning "A depends on B". The DAG check asserts:

* every edge names two recognized modules (``M0`` and up; ``M6`` is intentionally absent);
* the graph is a **directed acyclic graph** (no cycles);
* edge direction is **legal** — an edge must not point "upward" against the
  layering. We derive a topological level per module from the declared edges and
  require every edge to go from a higher level to a strictly lower one, which is
  exactly the acyclicity property surfaced as a direction error.

The **coverage gate** (Phase 12) reads the in-scope tiers from
``scope-and-tiers.md`` and asserts each in-scope module has fixture coverage,
measured against the ``tags`` of every fixture under ``core/compatibility/``
(cases *and* benchmarks). The might-do / won't-do tiers — including the RFC-2119
MAY temporal mutations — are excluded from the gate by construction (they are not
listed under the in-scope tier headings).
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import yaml

_FENCE_RE = re.compile(r"```dependency-graph\n(.*?)```", re.DOTALL)
_EDGE_RE = re.compile(r"^\s*(M\d+)\s*-->\s*(M\d+)\s*$")
_MODULE_RE = re.compile(r"^M\d+$")
_MODULE_TOKEN_RE = re.compile(r"\bM\d+\b")

# The three in-scope tier headings in scope-and-tiers.md, normalized to lower case.
# Any module mentioned under one of these (until the next "### " heading) is
# treated as in-scope for the coverage gate.
_IN_SCOPE_TIERS = ("mvp", "fast-follow", "definitely-do")


class DepGraphFailure(Exception):
    pass


def parse_edges(markdown: str) -> list[tuple[str, str]]:
    """Extract the (depends-on) edges from the dependency-graph fenced block."""
    match = _FENCE_RE.search(markdown)
    if not match:
        raise DepGraphFailure(
            "no ```dependency-graph fenced block found in the spec file"
        )
    edges: list[tuple[str, str]] = []
    for lineno, line in enumerate(match.group(1).splitlines(), start=1):
        if not line.strip():
            continue
        edge = _EDGE_RE.match(line)
        if not edge:
            raise DepGraphFailure(
                f"dependency-graph line {lineno} is not a valid 'A --> B' edge: {line!r}"
            )
        edges.append((edge.group(1), edge.group(2)))
    if not edges:
        raise DepGraphFailure("dependency-graph block declares no edges")
    return edges


def _find_cycle(edges: list[tuple[str, str]]) -> list[str] | None:
    """Return a cycle path if the directed graph has one, else None."""
    adjacency: dict[str, list[str]] = {}
    for src, dst in edges:
        adjacency.setdefault(src, []).append(dst)
        adjacency.setdefault(dst, [])

    WHITE, GRAY, BLACK = 0, 1, 2
    color = dict.fromkeys(adjacency, WHITE)
    stack: list[str] = []

    def visit(node: str) -> list[str] | None:
        color[node] = GRAY
        stack.append(node)
        for neighbor in adjacency[node]:
            if color[neighbor] == GRAY:
                idx = stack.index(neighbor)
                return [*stack[idx:], neighbor]
            if color[neighbor] == WHITE:
                cycle = visit(neighbor)
                if cycle:
                    return cycle
        color[node] = BLACK
        stack.pop()
        return None

    for node in sorted(adjacency):
        if color[node] == WHITE:
            cycle = visit(node)
            if cycle:
                return cycle
    return None


def check(markdown: str) -> list[str]:
    """Validate the graph; return a list of error strings (empty == OK)."""
    errors: list[str] = []
    try:
        edges = parse_edges(markdown)
    except DepGraphFailure as exc:
        return [str(exc)]

    for src, dst in edges:
        if not _MODULE_RE.match(src):
            errors.append(f"unrecognized module on left of edge: {src!r}")
        if not _MODULE_RE.match(dst):
            errors.append(f"unrecognized module on right of edge: {dst!r}")
        if src == dst:
            errors.append(f"self-dependency is illegal: {src} --> {dst}")

    cycle = _find_cycle(edges)
    if cycle:
        errors.append("dependency graph is not a DAG; cycle: " + " --> ".join(cycle))

    return errors


# --- coverage gate ---------------------------------------------------------


def parse_in_scope_modules(scope_markdown: str) -> set[str]:
    """Return the set of in-scope module tokens (``M0`` and up), read from the
    three in-scope tier sections of ``scope-and-tiers.md``.

    A module is in scope iff it is mentioned under an ``MVP`` / ``Fast-follow`` /
    ``Definitely-do`` ``### `` heading (until the next ``### `` heading).
    Cross-process cache coherence is ``M14`` and is picked up by the normal
    ``M\\d+`` token scan.
    """
    in_scope: set[str] = set()
    current_in_scope = False
    for line in scope_markdown.splitlines():
        heading = re.match(r"^###\s+(.*?)\s*$", line)
        if heading:
            title = heading.group(1).strip().lower()
            current_in_scope = title in _IN_SCOPE_TIERS
            continue
        if not current_in_scope:
            continue
        for token in _MODULE_TOKEN_RE.findall(line):
            in_scope.add(token)
    if not in_scope:
        raise DepGraphFailure(
            "no in-scope modules found under the MVP / fast-follow / definitely-do "
            "headings of scope-and-tiers.md"
        )
    return in_scope


def _fixture_tags(compatibility_root: Path) -> set[str]:
    """Collect the lower-cased ``tags`` of every fixture under compatibility/.

    Scans both ``cases/`` and ``benchmarks/`` (M13 fixtures cover M13). A fixture
    that does not parse to a mapping, or that carries no ``tags``, contributes
    nothing.
    """
    tags: set[str] = set()
    for subdir in ("cases", "benchmarks"):
        root = compatibility_root / subdir
        if not root.is_dir():
            continue
        for path in sorted(root.glob("**/*.yaml")) + sorted(root.glob("**/*.yml")):
            try:
                doc = yaml.safe_load(path.read_text(encoding="utf-8"))
            except yaml.YAMLError:
                continue
            if not isinstance(doc, dict):
                continue
            for tag in doc.get("tags", []):
                if isinstance(tag, str):
                    tags.add(tag.strip().lower())
    return tags


def coverage_errors(scope_markdown: str, compatibility_root: Path) -> list[str]:
    """Assert every in-scope module has >=1 fixture tagged to it.

    Returns a list of error strings (empty == fully covered).
    """
    try:
        in_scope = parse_in_scope_modules(scope_markdown)
    except DepGraphFailure as exc:
        return [str(exc)]

    fixture_tags = _fixture_tags(compatibility_root)
    if not fixture_tags:
        return [f"no fixture tags discovered under {compatibility_root}"]

    uncovered = sorted(
        module for module in in_scope if module.lower() not in fixture_tags
    )
    return [
        f"in-scope module {module} has no fixture tagged to it "
        f"(expected at least one fixture with tag {module.lower()!r})"
        for module in uncovered
    ]


def run_dag_check(spec_path: Path) -> int:
    markdown = spec_path.read_text(encoding="utf-8")
    errors = check(markdown)
    if errors:
        print(
            f"dependency-graph check FAILED ({len(errors)} problem(s)):",
            file=sys.stderr,
        )
        for error in errors:
            print(f"  - {error}", file=sys.stderr)
        return 1

    edges = parse_edges(markdown)
    modules = sorted({m for edge in edges for m in edge})
    print(
        f"dependency-graph OK: DAG with legal directions "
        f"({len(modules)} modules, {len(edges)} edges)"
    )
    return 0


def run_coverage(spec_dir: Path, compatibility_root: Path) -> int:
    graph_path = spec_dir / "dependency-graph.md"
    scope_path = spec_dir / "scope-and-tiers.md"
    for required in (graph_path, scope_path):
        if not required.is_file():
            print(f"not a file: {required}", file=sys.stderr)
            return 2
    if not compatibility_root.is_dir():
        print(f"not a directory: {compatibility_root}", file=sys.stderr)
        return 2

    # The coverage gate runs ON TOP OF the DAG check.
    dag_rc = run_dag_check(graph_path)

    scope_markdown = scope_path.read_text(encoding="utf-8")
    errors = coverage_errors(scope_markdown, compatibility_root)
    if errors:
        print(
            f"coverage gate FAILED ({len(errors)} uncovered module(s)):",
            file=sys.stderr,
        )
        for error in errors:
            print(f"  - {error}", file=sys.stderr)
        return 1 if dag_rc == 0 else dag_rc

    in_scope = parse_in_scope_modules(scope_markdown)
    print(
        f"coverage gate OK: every in-scope module is covered "
        f"({len(in_scope)} module(s) across MVP / fast-follow / definitely-do)"
    )
    return dag_rc


def main(argv: list[str]) -> int:
    if argv and argv[0] == "--coverage":
        rest = argv[1:]
        if len(rest) != 2:
            print(
                "usage: python -m reference_harness.dep_graph_check --coverage "
                "<spec-dir> <compatibility-dir>",
                file=sys.stderr,
            )
            return 2
        return run_coverage(Path(rest[0]), Path(rest[1]))

    if len(argv) != 1:
        print(
            "usage: python -m reference_harness.dep_graph_check "
            "<dependency-graph.md>\n"
            "   or: python -m reference_harness.dep_graph_check --coverage "
            "<spec-dir> <compatibility-dir>",
            file=sys.stderr,
        )
        return 2
    spec_path = Path(argv[0])
    if not spec_path.is_file():
        print(f"not a file: {spec_path}", file=sys.stderr)
        return 2
    return run_dag_check(spec_path)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
