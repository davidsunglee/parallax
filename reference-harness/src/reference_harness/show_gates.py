"""Display the resolved verification-command graph::

    uv run python -m reference_harness.show_gates <justfile-dir> [recipe ...]

Aggregates are listed first, because they are the entry points, and each one
names the execution recipes its closure actually runs — the answer to "what does
this gate already cover?" that otherwise requires reading the orchestrator's
file.

Contract violations are flagged in place rather than suppressed: a declaration
its own closure outruns, and an aggregate that composes nothing. The report
describes the graph it finds, not only a conforming one.
"""

from __future__ import annotations

import sys
from pathlib import Path

from reference_harness.gate_graph import (
    GateGraph,
    GateGraphError,
    Recipe,
    ResolvedRecipe,
    load_graph,
)

__all__ = ["main", "render"]

_UNCLASSIFIED = "unclassified"
_COMPOSES_NOTHING = "composes nothing: no command body and no dependency"


def _signature(recipe: Recipe) -> str:
    parameters = "".join(f" <{parameter}>" for parameter in recipe.parameters)
    private = " (private)" if recipe.private else ""
    return f"{recipe.name}{parameters}{private}"


def _classification_line(resolved: ResolvedRecipe) -> str:
    line = f"runtime: {resolved.runtime_class or _UNCLASSIFIED}"
    if resolved.understated_runtime_class is not None:
        declared = ", ".join(sorted(resolved.recipe.declared_runtime_classes))
        line += f"   understated (declared: {declared})"
    scheduling = sorted(resolved.recipe.declared_scheduling_classes)
    if scheduling:
        line += f"   scheduling: {', '.join(scheduling)}"
    return line


def _describe(resolved: ResolvedRecipe) -> list[str]:
    recipe = resolved.recipe
    lines = [f"  {_signature(recipe)}", f"    {_classification_line(resolved)}"]
    if recipe.doc is not None:
        lines.append(f"    doc: {recipe.doc}")
    if recipe.role == "execution":
        if recipe.dependencies:
            lines.append(f"    prerequisites: {', '.join(recipe.dependencies)}")
        lines.append(f"    commands: {len(recipe.body)}")
    elif recipe.dependencies:
        lines.append(f"    dependencies: {', '.join(recipe.dependencies)}")
        owners = resolved.execution_owners
        lines.append(f"    execution owners ({len(owners)}):")
        lines.extend(f"      - {owner}" for owner in owners)
    else:
        lines.append(f"    {_COMPOSES_NOTHING}")
    return lines


def render(graph: GateGraph, names: list[str]) -> list[str]:
    """The report for *names*, or for the whole graph when *names* is empty."""
    chosen = names or [recipe.name for recipe in graph.recipes]
    selected = [graph.resolve(name) for name in chosen]
    aggregates = [resolved for resolved in selected if resolved.recipe.role == "aggregate"]
    executions = [resolved for resolved in selected if resolved.recipe.role == "execution"]

    lines = [f"gate graph: {graph.source}", ""]
    for role_name, members in (("aggregate", aggregates), ("execution", executions)):
        if not members:
            continue
        lines.append(f"{role_name} recipes ({len(members)})")
        for resolved in members:
            lines.append("")
            lines.extend(_describe(resolved))
        lines.append("")
    lines.append(
        f"{len(selected)} recipe(s): {len(executions)} execution, {len(aggregates)} aggregate"
    )
    return lines


def _usage() -> str:
    return "usage: python -m reference_harness.show_gates <justfile-dir> [recipe ...]"


def main(argv: list[str]) -> int:
    """Exit codes: 0 — the report was rendered; 1 — the graph could not be
    resolved; 2 — usage error (argument count, missing directory, or a recipe
    the graph does not declare)."""
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
