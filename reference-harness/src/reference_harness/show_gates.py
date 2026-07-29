"""Display the resolved verification-command graph::

    uv run python -m reference_harness.show_gates <justfile-dir> [recipe ...]

Aggregates are listed first, because they are the entry points, and each one
names the execution recipes its closure actually runs — the answer to "what does
this gate already cover?" that otherwise requires reading the orchestrator's
file. Execution recipes follow with their prerequisites and command counts.
Naming recipes narrows the output to those recipes.
"""

from __future__ import annotations

import sys
from pathlib import Path

from reference_harness.gate_graph import GateGraph, GateGraphError, Recipe, load_graph

__all__ = ["main", "render"]


def _signature(recipe: Recipe) -> str:
    parameters = "".join(f" <{parameter}>" for parameter in recipe.parameters)
    private = " (private)" if recipe.private else ""
    return f"{recipe.name}{parameters}{private}"


def _classes(graph: GateGraph, recipe: Recipe) -> str:
    line = f"runtime: {graph.runtime_class(recipe.name)}"
    scheduling = sorted(recipe.scheduling_classes)
    if scheduling:
        line += f"   scheduling: {', '.join(scheduling)}"
    return line


def _describe(graph: GateGraph, recipe: Recipe) -> list[str]:
    lines = [f"  {_signature(recipe)}", f"    {_classes(graph, recipe)}"]
    if recipe.doc is not None:
        lines.append(f"    doc: {recipe.doc}")
    if recipe.role == "aggregate":
        lines.append(f"    dependencies: {', '.join(recipe.dependencies)}")
        closure = graph.closure(recipe.name)
        owners = [owned.name for owned in closure if owned.role == "execution"]
        lines.append(f"    execution owners ({len(owners)}):")
        lines.extend(f"      - {owner}" for owner in owners)
    else:
        if recipe.dependencies:
            lines.append(f"    prerequisites: {', '.join(recipe.dependencies)}")
        lines.append(f"    commands: {len(recipe.body)}")
    return lines


def render(graph: GateGraph, names: list[str]) -> list[str]:
    """The report for *names*, or for the whole graph when *names* is empty."""
    selected = [graph.recipe(name) for name in names] if names else list(graph.recipes)
    aggregates = [recipe for recipe in selected if recipe.role == "aggregate"]
    executions = [recipe for recipe in selected if recipe.role == "execution"]

    lines = [f"gate graph: {graph.source}", ""]
    for role_name, group in (("aggregate", aggregates), ("execution", executions)):
        if not group:
            continue
        lines.append(f"{role_name} recipes ({len(group)})")
        for recipe in group:
            lines.append("")
            lines.extend(_describe(graph, recipe))
        lines.append("")
    lines.append(
        f"{len(selected)} recipe(s): {len(executions)} execution, {len(aggregates)} aggregate"
    )
    return lines


def _usage() -> str:
    return "usage: python -m reference_harness.show_gates <justfile-dir> [recipe ...]"


def main(argv: list[str]) -> int:
    """CLI entry point.

    Exit codes: 0 — the report was rendered; 1 — the graph could not be
    resolved; 2 — usage error (argument count, missing directory, or a recipe
    the graph does not declare).
    """
    if not argv:
        print(_usage(), file=sys.stderr)
        return 2
    justfile_dir = Path(argv[0])
    if not justfile_dir.is_dir():
        print(f"not a directory: {justfile_dir}", file=sys.stderr)
        return 2

    try:
        graph = load_graph(justfile_dir)
    except (GateGraphError, OSError, ValueError) as exc:
        print(f"gate graph inspection FAILED: {exc}", file=sys.stderr)
        return 1

    names = argv[1:]
    try:
        lines = render(graph, names)
    except GateGraphError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    for line in lines:
        print(line)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
