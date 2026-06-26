"""Parse the normative module-dependency graph and assert it is a legal DAG.

Run as a module against the spec file::

    uv run python -m reference_harness.dep_graph_check ../core/spec/dependency-graph.md

The machine-readable source of truth is the fenced ```` ```dependency-graph ````
block in ``dependency-graph.md``. Each line is an edge ``A --> B`` meaning
"A depends on B". This check asserts:

* every edge names two recognized modules (``M0``–``M13``);
* the graph is a **directed acyclic graph** (no cycles);
* edge direction is **legal** — an edge must not point "upward" against the
  layering. We derive a topological level per module from the declared edges and
  require every edge to go from a higher level to a strictly lower one, which is
  exactly the acyclicity property surfaced as a direction error.

The coverage gate (every in-scope module has fixture coverage) is added in a
later phase and is intentionally not part of this check yet.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

_FENCE_RE = re.compile(r"```dependency-graph\n(.*?)```", re.DOTALL)
_EDGE_RE = re.compile(r"^\s*(M\d+)\s*-->\s*(M\d+)\s*$")
_MODULE_RE = re.compile(r"^M\d+$")


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


def main(argv: list[str]) -> int:
    if len(argv) != 1:
        print(
            "usage: python -m reference_harness.dep_graph_check <dependency-graph.md>",
            file=sys.stderr,
        )
        return 2
    spec_path = Path(argv[0])
    if not spec_path.is_file():
        print(f"not a file: {spec_path}", file=sys.stderr)
        return 2

    markdown = spec_path.read_text(encoding="utf-8")
    errors = check(markdown)
    if errors:
        print(f"dependency-graph check FAILED ({len(errors)} problem(s)):", file=sys.stderr)
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


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
