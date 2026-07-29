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
from typing import Any, Literal, NamedTuple

__all__ = [
    "OPERATIONS",
    "RUNTIME_CLASSES",
    "GateGraph",
    "GateGraphError",
    "Recipe",
    "RecipeName",
    "RuntimeClass",
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

RuntimeClass = Literal["fast", "medium", "slow"]
"""One relative execution duration."""

RUNTIME_CLASSES: tuple[RuntimeClass, ...] = ("fast", "medium", "slow")
"""Every runtime class, ordered fastest to slowest."""

_JUSTFILE_NAME = "justfile"

_OPERATION_TOKENS: tuple[tuple[str, ...], ...] = tuple(
    sorted((tuple(operation.split("-")) for operation in OPERATIONS), key=len, reverse=True)
)


class GateGraphError(Exception):
    """The command graph could not be resolved, or a recipe was not found in it."""


class RecipeName(NamedTuple):
    """A command name decomposed into the grammar's three slots."""

    scope: str | None
    operation: str
    qualifier: str | None


def _slowest(candidates: Iterable[str]) -> RuntimeClass | None:
    declared = set(candidates)
    for runtime_class in reversed(RUNTIME_CLASSES):
        if runtime_class in declared:
            return runtime_class
    return None


def _match_operation(tokens: Sequence[str]) -> tuple[str, str | None] | None:
    for candidate in _OPERATION_TOKENS:
        if tuple(tokens[: len(candidate)]) == candidate:
            qualifier = "-".join(tokens[len(candidate) :])
            return "-".join(candidate), qualifier or None
    return None


def parse_name(name: str) -> RecipeName:
    """Decompose a recipe name into its scope, operation, and qualifier.

    The operation is matched against the closed vocabulary, longest spelling
    first, so ``format-check`` is one operation rather than ``format`` with a
    ``check`` qualifier. A name whose operation slot holds no vocabulary entry
    still decomposes — the whole slot becomes the operation and the qualifier is
    ``None`` — so a caller can report a non-canonical operation instead of
    failing to read the graph that contains it.
    """
    tokens = name.split("-")
    matched = _match_operation(tokens)
    if matched is not None:
        operation, qualifier = matched
        return RecipeName(None, operation, qualifier)
    if len(tokens) == 1:
        return RecipeName(None, name, None)
    matched = _match_operation(tokens[1:])
    if matched is not None:
        operation, qualifier = matched
        return RecipeName(tokens[0], operation, qualifier)
    return RecipeName(tokens[0], "-".join(tokens[1:]), None)


@dataclass(frozen=True)
class Recipe:
    """One recipe as the orchestrator reports it, with its name decomposed.

    ``role`` follows the presence of a command body alone, so a recipe with
    neither a body nor a dependency reports ``aggregate`` — an aggregate that
    composes nothing. That is a contract violation for a caller to report, not a
    shape this reader declines to describe.
    """

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
    def declared_runtime_classes(self) -> frozenset[RuntimeClass]:
        """The runtime classes this recipe declares. Empty and plural are both
        representable; judging either is the caller's job."""
        return frozenset(
            runtime_class for runtime_class in RUNTIME_CLASSES if runtime_class in self.groups
        )

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

    def runtime_class(self, name: str) -> RuntimeClass | None:
        """*name*'s effective runtime class — the slowest one declared anywhere
        in its closure — or ``None`` when no recipe in that closure declares
        one."""
        return _slowest(
            runtime_class
            for recipe in self.closure(name)
            for runtime_class in recipe.declared_runtime_classes
        )

    def understated_runtime_class(self, name: str) -> RuntimeClass | None:
        """*name*'s effective runtime class when that is slower than every class
        *name* itself declares, and ``None`` otherwise.

        A prerequisite makes running a recipe cost what the prerequisite costs,
        so an execution recipe understates its runtime the same way an aggregate
        does. A recipe declaring nothing understates nothing: what to require of
        an absent declaration is the caller's rule, not the graph's.
        """
        declared = _slowest(self.recipe(name).declared_runtime_classes)
        effective = self.runtime_class(name)
        if declared is None or effective is None:
            return None
        if RUNTIME_CLASSES.index(effective) <= RUNTIME_CLASSES.index(declared):
            return None
        return effective


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
    parsed = parse_name(name)
    return Recipe(
        name=name,
        scope=parsed.scope,
        operation=parsed.operation,
        qualifier=parsed.qualifier,
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
