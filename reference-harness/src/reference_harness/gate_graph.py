"""Resolved view of the repository's verification-command graph.

The root ``justfile`` is the authoritative executable dependency graph, so gate
tooling reads it rather than a second manifest. This module is that reader: it
resolves ``just --dump --dump-format json``, which exposes each recipe's
dependencies, body, parameters, and attributes structurally.

Scheduling and runtime classes travel as ``[group(...)]`` attributes and the
human description as ``[doc(...)]``. A leading comment is deliberately NOT a
description source: the dump truncates a comment block to the single line above
the recipe, so a recipe without ``[doc(...)]`` reports no description at all
rather than a fragment of one.

Grammar and vocabulary conformance is not judged here: a name outside the
vocabulary still decomposes, so a caller can report on the graph it finds rather
than only on a conforming one.
"""

from __future__ import annotations

import json
import subprocess
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

__all__ = [
    "OPERATIONS",
    "RUNTIME_CLASSES",
    "UNCLASSIFIED",
    "GateGraph",
    "GateGraphError",
    "Recipe",
    "load_graph",
    "parse_name",
]

OPERATIONS: tuple[str, ...] = (
    "audit",
    "build",
    "check",
    "coverage",
    "format",
    "format-check",
    "lint",
    "report",
    "show",
    "test",
    "typecheck",
)
"""The closed operation vocabulary."""

RUNTIME_CLASSES: tuple[str, ...] = ("fast", "medium", "slow")
"""Relative execution durations, ordered fastest to slowest."""

UNCLASSIFIED = "unclassified"
"""Reported runtime class when nothing in a closure declares one."""

_JUSTFILE_NAME = "justfile"

_OPERATION_TOKENS: tuple[tuple[str, ...], ...] = tuple(
    sorted((tuple(operation.split("-")) for operation in OPERATIONS), key=len, reverse=True)
)


class GateGraphError(Exception):
    """The command graph could not be resolved, or a recipe was not found in it."""


def _match_operation(tokens: Sequence[str]) -> tuple[str, str | None] | None:
    for candidate in _OPERATION_TOKENS:
        if tuple(tokens[: len(candidate)]) == candidate:
            qualifier = "-".join(tokens[len(candidate) :])
            return "-".join(candidate), qualifier or None
    return None


def parse_name(name: str) -> tuple[str | None, str, str | None]:
    """Decompose a recipe name into ``(scope, operation, qualifier)``.

    The operation is matched against the closed vocabulary, longest spelling
    first, so ``format-check`` is one operation rather than ``format`` with a
    ``check`` qualifier. A name whose operation slot holds no vocabulary entry
    still decomposes — the whole slot becomes the operation and the qualifier is
    ``None`` — so a caller can tell ``core-dep-graph`` apart from ``core`` and
    report it as the non-canonical operation ``dep-graph``.
    """
    tokens = name.split("-")
    matched = _match_operation(tokens)
    if matched is not None:
        operation, qualifier = matched
        return None, operation, qualifier
    if len(tokens) == 1:
        return None, name, None
    matched = _match_operation(tokens[1:])
    if matched is not None:
        operation, qualifier = matched
        return tokens[0], operation, qualifier
    return tokens[0], "-".join(tokens[1:]), None


@dataclass(frozen=True)
class Recipe:
    """One recipe as the orchestrator reports it, with its name decomposed."""

    name: str
    scope: str | None
    operation: str
    qualifier: str | None
    role: Literal["execution", "aggregate"]
    groups: frozenset[str]
    doc: str | None
    dependencies: tuple[str, ...]
    body: tuple[str, ...]
    parameters: tuple[str, ...]
    private: bool

    @property
    def declared_runtime_classes(self) -> frozenset[str]:
        """The runtime classes this recipe declares. Empty and plural are both
        representable; judging either is the caller's job."""
        return self.groups & frozenset(RUNTIME_CLASSES)

    @property
    def scheduling_classes(self) -> frozenset[str]:
        """Every declared group that is not a runtime class."""
        return self.groups - frozenset(RUNTIME_CLASSES)


class GateGraph:
    """Every recipe in one ``justfile``, resolvable by name and by closure."""

    def __init__(self, source: Path, recipes: Iterable[Recipe]) -> None:
        self._by_name = {recipe.name: recipe for recipe in recipes}
        self.source = source
        self.recipes = tuple(sorted(self._by_name.values(), key=lambda recipe: recipe.name))

    def recipe(self, name: str) -> Recipe:
        """The recipe called *name*, raising ``GateGraphError`` when the graph
        declares no such recipe."""
        found = self._by_name.get(name)
        if found is None:
            known = ", ".join(recipe.name for recipe in self.recipes)
            raise GateGraphError(f"unknown recipe {name!r}; the graph declares: {known}")
        return found

    def closure(self, name: str) -> tuple[Recipe, ...]:
        """*name* and everything it reaches, in the order the orchestrator runs
        them: dependencies depth-first and left to right, each recipe once, the
        named recipe last."""
        order: list[Recipe] = []
        visited: set[str] = set()

        def visit(current: str) -> None:
            if current in visited:
                return
            visited.add(current)
            recipe = self.recipe(current)
            for dependency in recipe.dependencies:
                visit(dependency)
            order.append(recipe)

        visit(name)
        return tuple(order)

    def runtime_class(self, name: str) -> str:
        """The slowest runtime class declared anywhere in *name*'s closure, or
        ``UNCLASSIFIED`` when no recipe in it declares one."""
        declared = {
            runtime_class
            for recipe in self.closure(name)
            for runtime_class in recipe.declared_runtime_classes
        }
        for candidate in reversed(RUNTIME_CLASSES):
            if candidate in declared:
                return candidate
        return UNCLASSIFIED


def _render_expression(expression: Any) -> str:
    """Reproduce one dumped expression.

    ``{{name}}`` variable interpolation — the only form this repository's gates
    use — round-trips exactly. Any other expression form is rendered
    structurally, which keeps rendering total without claiming to reproduce the
    source.
    """
    if isinstance(expression, str):
        return expression
    if isinstance(expression, list):
        items: list[Any] = expression
        if len(items) == 2 and items[0] == "variable":
            return str(items[1])
        return " ".join(_render_expression(item) for item in items)
    return str(expression)


def _render_line(fragments: Sequence[Any]) -> str:
    rendered: list[str] = []
    for fragment in fragments:
        if isinstance(fragment, str):
            rendered.append(fragment)
        else:
            interpolation = " ".join(_render_expression(item) for item in fragment)
            rendered.append("{{" + interpolation + "}}")
    return "".join(rendered)


def _attribute_values(attributes: Sequence[Any], key: str) -> list[str]:
    return [
        str(attribute[key])
        for attribute in attributes
        if isinstance(attribute, Mapping) and key in attribute
    ]


def _recipe_from_dump(name: str, entry: Mapping[str, Any]) -> Recipe:
    attributes: Sequence[Any] = entry.get("attributes", [])
    docs = _attribute_values(attributes, "doc")
    body = tuple(_render_line(line) for line in entry.get("body", []))
    scope, operation, qualifier = parse_name(name)
    return Recipe(
        name=name,
        scope=scope,
        operation=operation,
        qualifier=qualifier,
        role="execution" if body else "aggregate",
        groups=frozenset(_attribute_values(attributes, "group")),
        doc=docs[0] if docs else None,
        dependencies=tuple(
            str(dependency["recipe"]) for dependency in entry.get("dependencies", [])
        ),
        body=body,
        parameters=tuple(str(parameter["name"]) for parameter in entry.get("parameters", [])),
        private=bool(entry.get("private", False)),
    )


def load_graph(justfile_dir: Path) -> GateGraph:
    """Resolve the ``justfile`` in *justfile_dir* through the orchestrator's own
    JSON dump.

    Raises ``GateGraphError`` when the directory holds no ``justfile``, the
    orchestrator is unavailable, or it rejects the file.
    """
    justfile = (justfile_dir / _JUSTFILE_NAME).resolve()
    if not justfile.is_file():
        raise GateGraphError(f"not a file: {justfile}")
    command = ["just", "--justfile", str(justfile), "--dump", "--dump-format", "json"]
    try:
        completed = subprocess.run(command, capture_output=True, text=True, check=False)
    except OSError as exc:
        raise GateGraphError(f"could not run {command[0]!r}: {exc}") from exc
    if completed.returncode != 0:
        raise GateGraphError(f"{justfile} did not dump: {completed.stderr.strip()}")
    dump: dict[str, Any] = json.loads(completed.stdout)
    recipes: dict[str, Any] = dump.get("recipes", {})
    return GateGraph(justfile, [_recipe_from_dump(name, entry) for name, entry in recipes.items()])
