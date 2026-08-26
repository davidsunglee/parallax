"""Resolved view of the repository's verification-command graph.

The root ``justfile`` is the authoritative executable dependency graph, so gate
tooling reads it rather than a second manifest. This module is that reader: it
resolves ``just --dump --dump-format json``, which exposes each recipe's
dependencies, body, parameters, and attributes structurally.

Runtime and scheduling classes travel as ``[metadata(...)]`` values prefixed
``runtime:`` and ``scheduling:``, and the human description as ``[doc(...)]``.
``[group(...)]`` is deliberately NOT a class carrier: ``just`` also organizes
``--list`` by group, so classifying recipes that way would segregate the listing
by class and repeat every recipe once per class it declares. A leading comment is
deliberately NOT a description source: the dump truncates a comment block to the
single line above the recipe, so a recipe without ``[doc(...)]`` reports no
description at all rather than a fragment of one.

Grammar and vocabulary conformance is not judged here: a name outside the
vocabulary still decomposes, so a caller can report on the graph it finds rather
than only on a conforming one.
"""

from __future__ import annotations

import json
import re
import subprocess
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, NamedTuple

__all__ = [
    "BLOCKING_OPERATIONS",
    "OPERATIONS",
    "RUNTIME_CLASSES",
    "GateGraph",
    "GateGraphError",
    "Recipe",
    "ResolvedRecipe",
    "RuntimeClass",
    "load_graph",
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

BLOCKING_OPERATIONS: frozenset[str] = frozenset(
    {"audit", "build", "check", "coverage", "format-check", "lint", "test", "typecheck"}
)
"""The operations whose purpose is a verdict.

The rest rewrite, describe, or display, and pass no judgement about the subject
they examine: they belong to no gate, so nothing requires them to be covered and
nothing forbids an aggregate from depending on one for its output. That one of
them may still exit non-zero on being unable to produce its output at all (§2)
does not make it blocking — an exit code is not what the partition is drawn on.
Blocking is a property of an operation rather than of a graph, so it is declared
beside the vocabulary it partitions."""

RuntimeClass = Literal["fast", "medium", "slow"]
"""One relative execution duration."""

RUNTIME_CLASSES: tuple[RuntimeClass, ...] = ("fast", "medium", "slow")
"""Every runtime class, ordered fastest to slowest."""

_JUSTFILE_NAME = "justfile"
_RUNTIME_PREFIX = "runtime:"
_SCHEDULING_PREFIX = "scheduling:"
_INTERPOLATION_RE = re.compile(r"\{\{([A-Za-z_][A-Za-z0-9_]*)\}\}")

_OPERATION_TOKENS: tuple[tuple[str, ...], ...] = tuple(
    sorted((tuple(operation.split("-")) for operation in OPERATIONS), key=len, reverse=True)
)


class GateGraphError(Exception):
    """The command graph could not be resolved, or a recipe was not found in it."""


class _RecipeName(NamedTuple):
    """A command name decomposed into the grammar's three slots."""

    scope: str | None
    operation: str
    qualifier: str | None


def _slowest(candidates: Iterable[RuntimeClass]) -> RuntimeClass | None:
    return max(candidates, key=RUNTIME_CLASSES.index, default=None)


def _fastest(candidates: Iterable[RuntimeClass]) -> RuntimeClass | None:
    return min(candidates, key=RUNTIME_CLASSES.index, default=None)


def _declared_classes(metadata: Iterable[str], prefix: str) -> frozenset[str]:
    return frozenset(value.removeprefix(prefix) for value in metadata if value.startswith(prefix))


def _understated(
    declared: frozenset[RuntimeClass], effective: RuntimeClass | None
) -> RuntimeClass | None:
    optimistic = _fastest(declared)
    if optimistic is None or effective is None:
        return None
    if RUNTIME_CLASSES.index(effective) <= RUNTIME_CLASSES.index(optimistic):
        return None
    return effective


def _match_operation(tokens: Sequence[str]) -> tuple[str, str | None] | None:
    for candidate in _OPERATION_TOKENS:
        if tuple(tokens[: len(candidate)]) == candidate:
            qualifier = "-".join(tokens[len(candidate) :])
            return "-".join(candidate), qualifier or None
    return None


def _parse_name(name: str) -> _RecipeName:
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
        return _RecipeName(None, operation, qualifier)
    if len(tokens) == 1:
        return _RecipeName(None, name, None)
    matched = _match_operation(tokens[1:])
    if matched is not None:
        operation, qualifier = matched
        return _RecipeName(tokens[0], operation, qualifier)
    return _RecipeName(tokens[0], "-".join(tokens[1:]), None)


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
    metadata: tuple[str, ...]
    doc: str | None
    dependencies: tuple[str, ...]
    body: tuple[str, ...]
    parameters: tuple[str, ...]
    private: bool

    @property
    def declared_runtime_classes(self) -> frozenset[RuntimeClass]:
        """The runtime classes this recipe declares. Empty and plural are both
        representable; judging either is the caller's job. A ``runtime:`` value
        outside the vocabulary is not a runtime class and stays in ``metadata``
        for a caller to reject."""
        declared = _declared_classes(self.metadata, _RUNTIME_PREFIX)
        return frozenset(
            runtime_class for runtime_class in RUNTIME_CLASSES if runtime_class in declared
        )

    @property
    def declared_scheduling_classes(self) -> frozenset[str]:
        """The scheduling classes this recipe declares. A test recipe declaring
        one owns that class's execution; one declaring none is a focused
        selector, which the name alone cannot distinguish."""
        return _declared_classes(self.metadata, _SCHEDULING_PREFIX)


@dataclass(frozen=True)
class ResolvedRecipe:
    """One recipe together with what its dependency closure implies, worked out
    in a single walk.

    ``closure`` is the recipe and everything it reaches, in run order.
    ``runtime_class`` is the slowest class declared anywhere in that closure, or
    ``None`` when nothing in it declares one. ``understated_runtime_class`` is
    that effective class when the recipe itself declares a faster one, and
    ``None`` otherwise — a recipe declaring nothing understates nothing, since
    what to require of an absent declaration is the caller's rule. A recipe
    declaring several classes is judged by the fastest of them, because each
    declared class is a claim about the whole cost.
    """

    recipe: Recipe
    closure: tuple[Recipe, ...]
    runtime_class: RuntimeClass | None
    understated_runtime_class: RuntimeClass | None

    @property
    def execution_owners(self) -> tuple[str, ...]:
        """The names of every recipe in the closure that carries a command body,
        in run order — what running this recipe actually executes."""
        return tuple(owned.name for owned in self.closure if owned.role == "execution")


class GateGraph:
    """Every recipe in one ``justfile``, addressable by name and resolvable
    together with what its dependency closure implies."""

    def __init__(
        self, source: Path, recipes: Iterable[Recipe], assignments: Mapping[str, str]
    ) -> None:
        self._by_name = {recipe.name: recipe for recipe in recipes}
        self._assignments = dict(assignments)
        self.source = source
        self.recipes = tuple(sorted(self._by_name.values(), key=lambda recipe: recipe.name))

    @property
    def assignments(self) -> Mapping[str, str]:
        """Every variable the file assigns a literal value, by name."""
        return self._assignments

    def expand(self, text: str) -> str:
        """*text* with each ``{{name}}`` replaced by the value assigned to
        *name*.

        A body preserves its source spelling, so the path a recipe runs in is
        readable only once the file's own variables are substituted. An
        interpolation naming something other than an assigned variable is left
        as it stands.
        """
        return _INTERPOLATION_RE.sub(
            lambda match: self._assignments.get(match.group(1), match.group(0)), text
        )

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

    def resolve(self, name: str) -> ResolvedRecipe:
        """*name* with its closure and runtime classification worked out
        together.

        A prerequisite makes running a recipe cost what the prerequisite costs,
        so an execution recipe understates its runtime the same way an aggregate
        does; both are judged here.
        """
        recipe = self.recipe(name)
        closure = self.closure(name)
        effective = _slowest(
            runtime_class
            for reached in closure
            for runtime_class in reached.declared_runtime_classes
        )
        return ResolvedRecipe(
            recipe=recipe,
            closure=closure,
            runtime_class=effective,
            understated_runtime_class=_understated(recipe.declared_runtime_classes, effective),
        )


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


def _metadata_values(attributes: Sequence[Any]) -> tuple[str, ...]:
    """Every ``[metadata(...)]`` value, flattened — the attribute carries a list
    and may be repeated on one recipe."""
    values: list[str] = []
    for attribute in attributes:
        if isinstance(attribute, Mapping) and "metadata" in attribute:
            entries: Sequence[Any] = attribute["metadata"]
            values.extend(str(entry) for entry in entries)
    return tuple(values)


def _recipe_from_dump(name: str, entry: Mapping[str, Any]) -> Recipe:
    attributes: Sequence[Any] = entry.get("attributes", [])
    docs = _attribute_values(attributes, "doc")
    body = tuple(_render_line(line) for line in entry.get("body", []))
    parsed = _parse_name(name)
    return Recipe(
        name=name,
        scope=parsed.scope,
        operation=parsed.operation,
        qualifier=parsed.qualifier,
        role="execution" if body else "aggregate",
        metadata=_metadata_values(attributes),
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
    assignments: dict[str, Any] = dump.get("assignments", {})
    return GateGraph(
        justfile,
        [_recipe_from_dump(name, entry) for name, entry in recipes.items()],
        {name: str(entry["value"]) for name, entry in assignments.items() if "value" in entry},
    )
