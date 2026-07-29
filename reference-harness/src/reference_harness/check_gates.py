"""Fail when the repository's verification-command graph breaks the language
testing contract::

    uv run python -m reference_harness.check_gates <repository-root>

`core/spec/language-testing.md` fixes the command grammar, the operation
vocabulary, the two command roles, the scheduling partition, the runtime
declaration, the test-root structure, and the CI contract. Until something reads
the graph and fails on a breach, every one of those rules is a convention that
holds only while each author remembers it. This is the blocking check §8
requires over the graph.

Every rule is decided from the orchestrator's own dump, from the runner
configuration and test roots the graph itself locates, from the CI workflow, and
from the operational maps. Nothing is restated here that one of those already
states: a second description of the gates is what §8 forbids, and a checker that
carried its own copy of the recipe list would be one.
"""

from __future__ import annotations

import re
import sys
import tomllib
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from reference_harness.gate_graph import (
    OPERATIONS,
    RUNTIME_CLASSES,
    GateGraph,
    GateGraphError,
    Recipe,
    load_graph,
)

__all__ = [
    "BLOCKING_OPERATIONS",
    "CI_WORKFLOW",
    "OPERATIONAL_MAP",
    "RUNNER_ROOT_FILES",
    "SCHEDULING_GUARDS",
    "SUPPORT_DIRECTORY",
    "SURFACES",
    "TOOLING_SCOPES",
    "Finding",
    "audit",
    "main",
]

TOOLING_SCOPES: tuple[str, ...] = ("core", "harness")
"""The scopes that validate a shared artifact or maintain the repository's own
tooling. Every other scope is a language, discovered under ``languages/``."""

BLOCKING_OPERATIONS: frozenset[str] = frozenset(
    {"audit", "build", "check", "coverage", "format-check", "lint", "test", "typecheck"}
)
"""The operations whose purpose is a verdict. The rest rewrite, describe, or
display, belong to no gate, and are neither required of CI nor forbidden as an
aggregate's terminal dependency."""

SURFACES: Mapping[str, str] = {
    "unit": "unit",
    "compatibility": "compatibility",
    "api": "api",
    "dialect": "dialect",
    "provider-contract": "provider_contract",
    "distribution": "distribution",
}
"""The six primary semantic surfaces every language scope provides, as the
focused command's qualifier mapped to the directory holding that surface."""

SUPPORT_DIRECTORY = "_support"
"""The one non-surface directory a language scope's test root may hold."""

RUNNER_ROOT_FILES: frozenset[str] = frozenset({"conftest.py"})
"""The files the test runner requires at the root of a test tree, and therefore
the only files permitted directly under one."""

SCHEDULING_GUARDS: Mapping[str, str] = {"db": "database-access"}
"""The qualifier of the blocking check that confines each scheduling class's
defining resource to the entry points its scope designates.

A class is honest only while the resource that defines it is unreachable by any
other route, and that restriction has to be a blocking check of its own. Which
resource a class is about is a fact about the class, not about the graph, so it
is named here rather than derived: `db` is defined by live database access, and
the check confining it is `<scope>-check-database-access`. Where the check
itself looks — a fixture name, a set of seams — stays in that check; this
command only requires that one exists and that a class aggregate runs it."""

CI_WORKFLOW = Path(".github/workflows/ci.yml")
"""The workflow whose jobs must cover the required repository check graph."""

OPERATIONAL_MAP = "TESTING.md"
"""The operational map, at the repository root and in every language scope.

The graph, this map, and the CI job list are three descriptions of one fact —
which commands gate this repository and what runs them — so every pair is
compared. Editing two of the three consistently while the third goes stale
therefore fails, which is the only arrangement in which a map is worth reading.
"""

_RECIPE_LINE_RE = re.compile(r"^(?P<name>[A-Za-z_][A-Za-z0-9_-]*)[^:=\n]*:(?!=)", re.MULTILINE)
_JUST_INVOCATION_RE = re.compile(r"\bjust\s+(?P<recipe>[a-z][a-z0-9-]*)")
_CODE_SPAN_RE = re.compile(r"`([^`\n]+)`")
# A code span citing a command: the orchestrator, one recipe name, and whatever
# arguments follow. A span holding a placeholder rather than a name — the
# `<surface>` of a family of commands — matches nothing and cites nothing.
_CITED_COMMAND_RE = re.compile(r"^just (?P<recipe>[a-z][a-z0-9-]*)(?:\s.*)?$")

# The operation each recognized runner performs, longest spelling first so
# `ruff format --check` is read as `format-check` rather than as `format`. A tool
# absent from this table says nothing about the operation performed with it —
# §7 decides that by what an invocation does, which is why a body running
# `sql_lint` over the corpus is still one `check`.
_RUNNER_OPERATIONS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"\bruff format --check\b"), "format-check"),
    (re.compile(r"\bruff format\b"), "format"),
    (re.compile(r"\bruff check\b"), "lint"),
    (re.compile(r"\bmarkdownlint-cli2\b"), "lint"),
    (re.compile(r"\b(?:based)?pyright\b"), "typecheck"),
    (re.compile(r"\bpytest\b"), "test"),
    (re.compile(r"\buv build\b"), "build"),
    (re.compile(r"\bpip-audit\b"), "audit"),
    (re.compile(r"\bdiff-cover\b"), "coverage"),
)

_AGGREGATE_RANK = 0
_SCHEDULING_TEST_RANK = 1
_SURFACE_TEST_RANK = 2
_FOCUSED_TEST_RANK = 3
_EXECUTION_RANK = 4
_MUTATING_RANK = 5


@dataclass(frozen=True)
class Finding:
    """One breach of the contract, addressed by the drift code it reports."""

    code: str
    message: str

    def __str__(self) -> str:
        return f"[{self.code}] {self.message}"


@dataclass(frozen=True)
class _RunnerConfig:
    """One scope's test-runner configuration, as its packaging file declares it."""

    markers: tuple[str, ...]
    addopts: str
    testpaths: tuple[str, ...]


@dataclass(frozen=True)
class _Job:
    """One CI job, reduced to what the contract judges it by."""

    identifier: str
    invoked: tuple[str, ...]
    commands: tuple[str, ...]


@dataclass(frozen=True)
class _Repository:
    """The graph together with what the repository layout says about it."""

    root: Path
    graph: GateGraph
    public: tuple[Recipe, ...]
    language_scopes: tuple[str, ...]
    scheduling_classes: tuple[str, ...]

    @property
    def scopes(self) -> tuple[str, ...]:
        return TOOLING_SCOPES + self.language_scopes

    def declares(self, name: str) -> bool:
        return any(recipe.name == name for recipe in self.graph.recipes)

    def scope_classes(self, scope: str) -> tuple[str, ...]:
        declared = {
            scheduling_class
            for recipe in self.public
            if recipe.scope == scope
            for scheduling_class in recipe.declared_scheduling_classes
        }
        return tuple(sorted(declared))

    def module_dir(self, scope: str) -> Path | None:
        """Where *scope*'s module lives, or ``None`` when the file declares no
        path for it.

        A language scope is a directory under ``languages/`` by construction —
        that is where it was discovered. Any other scope names its own path in
        an assignment named after the scope, which is the file's own declaration
        rather than a convention restated here.
        """
        if scope in self.language_scopes:
            return self.root / "languages" / scope
        location = self.graph.assignments.get(scope)
        return None if location is None else self.root / location


def _runner_operation(command: str) -> str | None:
    for pattern, operation in _RUNNER_OPERATIONS:
        if pattern.search(command):
            return operation
    return None


def _is_scheduling_test(recipe: Recipe) -> bool:
    return recipe.operation == "test" and bool(recipe.declared_scheduling_classes)


def _is_focused_test(recipe: Recipe) -> bool:
    return recipe.operation == "test" and not recipe.declared_scheduling_classes


def _load_repository(root: Path, graph: GateGraph) -> _Repository:
    languages = root / "languages"
    language_scopes = (
        tuple(sorted(entry.name for entry in languages.iterdir() if entry.is_dir()))
        if languages.is_dir()
        else ()
    )
    public = tuple(recipe for recipe in graph.recipes if not recipe.private)
    classes = {
        scheduling_class
        for recipe in public
        for scheduling_class in recipe.declared_scheduling_classes
    }
    return _Repository(
        root=root,
        graph=graph,
        public=public,
        language_scopes=language_scopes,
        scheduling_classes=tuple(sorted(classes)),
    )


def _check_names(repository: _Repository) -> Iterator[Finding]:
    """§1's grammar and §2's closed vocabulary, over public commands."""
    known = set(repository.scopes)
    for recipe in repository.public:
        if recipe.operation not in OPERATIONS:
            yield Finding(
                "non-canonical-operation",
                f"`{recipe.name}` performs the operation `{recipe.operation}`, which is "
                f"outside the closed vocabulary ({', '.join(OPERATIONS)})",
            )
        if recipe.scope is not None and recipe.scope not in known:
            yield Finding(
                "unknown-scope",
                f"`{recipe.name}` names the scope `{recipe.scope}`; a scope is one of "
                f"{', '.join(sorted(known))}",
            )


def _section(recipe: Recipe, repository: _Repository) -> int | None:
    """Which top-level section of the file *recipe* belongs in, or ``None`` when
    its scope is not one the file has a section for."""
    if recipe.scope is None:
        return 1 if recipe.operation in BLOCKING_OPERATIONS else 2
    if recipe.scope in TOOLING_SCOPES:
        return 3 + TOOLING_SCOPES.index(recipe.scope)
    if recipe.scope in repository.language_scopes:
        return 3 + len(TOOLING_SCOPES) + repository.language_scopes.index(recipe.scope)
    return None


def _within_section(recipe: Recipe) -> int:
    if recipe.role == "aggregate":
        return _AGGREGATE_RANK
    if _is_scheduling_test(recipe):
        return _SCHEDULING_TEST_RANK
    if recipe.operation == "test":
        return _SURFACE_TEST_RANK if recipe.qualifier in SURFACES else _FOCUSED_TEST_RANK
    return _MUTATING_RANK if recipe.operation == "format" else _EXECUTION_RANK


def _source_order(repository: _Repository) -> list[Recipe]:
    """Every public recipe in the order the file declares it."""
    source = repository.graph.source.read_text(encoding="utf-8")
    lines = {
        match.group("name"): source.count("\n", 0, match.start())
        for match in _RECIPE_LINE_RE.finditer(source)
    }
    ordered = [recipe for recipe in repository.public if recipe.name in lines]
    ordered.sort(key=lambda recipe: lines[recipe.name])
    return ordered


def _check_order(repository: _Repository) -> Iterator[Finding]:
    """The file's declaration order, top-level sections first and each section's
    own progression second."""
    previous: tuple[Recipe, int, int] | None = None
    for recipe in _source_order(repository):
        section = _section(recipe, repository)
        if section is None:
            continue
        rank = _within_section(recipe)
        if previous is not None:
            earlier, earlier_section, earlier_rank = previous
            if section < earlier_section:
                yield Finding(
                    "section-order",
                    f"`{recipe.name}` is declared after `{earlier.name}`, which belongs to a "
                    f"later section: the file runs configuration, repository-wide commands, "
                    f"introspection and reports, then one section per scope",
                )
            elif section == earlier_section and rank < earlier_rank:
                yield Finding(
                    "scope-order",
                    f"`{recipe.name}` is declared after `{earlier.name}`, which belongs later "
                    f"in the same section: a section runs aggregates, scheduling-class test "
                    f"commands, the semantic-surface commands, other focused selectors, other "
                    f"execution commands, then mutating helpers",
                )
        previous = (recipe, section, rank)


def _required_aggregates(repository: _Repository) -> tuple[str, ...]:
    """Every command §7 requires to be dependency-only, that the graph declares."""
    required = ["check", *(f"check-{cls}" for cls in repository.scheduling_classes)]
    for scope in repository.scopes:
        required.append(f"{scope}-check")
        required.extend(f"{scope}-check-{cls}" for cls in repository.scope_classes(scope))
    return tuple(name for name in required if repository.declares(name))


def _check_roles(repository: _Repository) -> Iterator[Finding]:
    """§7's two roles, and the limit on what one execution body may do."""
    dependency_only = set(_required_aggregates(repository))
    for recipe in repository.public:
        if not recipe.body and not recipe.dependencies:
            yield Finding(
                "composes-nothing",
                f"`{recipe.name}` has no command body and no dependency; an aggregate that "
                f"composes nothing gates nothing",
            )
        if recipe.body and recipe.name in dependency_only:
            yield Finding(
                "aggregate-with-body",
                f"`{recipe.name}` composes other commands and carries a command body; an "
                f"aggregate cannot be composed without re-running that body",
            )
        if recipe.role != "execution":
            continue
        for line in recipe.body:
            performed = _runner_operation(line)
            if performed is not None and performed != recipe.operation:
                yield Finding(
                    "inlined-operation",
                    f"`{recipe.name}` performs `{performed}` in `{line.strip()}`, which is an "
                    f"operation its name does not declare",
                )
        if _is_scheduling_test(recipe):
            invocations = [line for line in recipe.body if _runner_operation(line) == "test"]
            if len(invocations) != 1:
                yield Finding(
                    "multiple-test-invocations",
                    f"`{recipe.name}` owns a scheduling class and makes {len(invocations)} "
                    f"test-runner invocations; a class is one selection, run once",
                )


def _check_scheduling(repository: _Repository) -> Iterator[Finding]:
    """§5's partition and §7's composition, read off the declarations rather than
    off the names."""
    graph = repository.graph
    for recipe in repository.public:
        for scheduling_class in sorted(recipe.declared_scheduling_classes):
            expected = f"{recipe.scope}-test-{scheduling_class}"
            if recipe.name != expected:
                yield Finding(
                    "misplaced-scheduling-class",
                    f"`{recipe.name}` declares the scheduling class `{scheduling_class}`; the "
                    f"command owning that class's execution is `{expected}`",
                )

    for recipe in repository.public:
        for dependency in recipe.dependencies:
            if _is_focused_test(graph.recipe(dependency)):
                yield Finding(
                    "focused-test-in-aggregate",
                    f"`{recipe.name}` depends on the focused selector `{dependency}`, which "
                    f"cuts across the scheduling partition and would be selected twice",
                )

    for scope in repository.scopes:
        classes = repository.scope_classes(scope)
        if scope in repository.language_scopes and not repository.declares(f"{scope}-check"):
            yield Finding(
                "missing-scope-check",
                f"`{scope}` exposes no `{scope}-check` aggregate; its language spec names one "
                f"complete verification command, and nothing else in the graph provides it",
            )
        for scheduling_class in classes:
            aggregate = f"{scope}-check-{scheduling_class}"
            if not repository.declares(aggregate):
                yield Finding(
                    "missing-class-aggregate",
                    f"`{scope}` declares the scheduling class `{scheduling_class}` but exposes "
                    f"no `{aggregate}` aggregate for it",
                )
                continue
            reached = {recipe.name for recipe in graph.closure(aggregate)}
            owner = f"{scope}-test-{scheduling_class}"
            if owner not in reached:
                yield Finding(
                    "missing-class-aggregate",
                    f"`{aggregate}` does not compose `{owner}`, so the class it names is not "
                    f"what it runs",
                )
            for other in classes:
                foreign = f"{scope}-test-{other}"
                if other != scheduling_class and foreign in reached:
                    yield Finding(
                        "foreign-test-in-aggregate",
                        f"`{aggregate}` composes `{foreign}`, which belongs to the "
                        f"`{other}` class; class selections must stay disjoint",
                    )
        yield from _check_scheduling_guard(repository, scope, classes)

    yield from _check_repository_aggregates(repository)


def _check_scheduling_guard(
    repository: _Repository, scope: str, classes: Sequence[str]
) -> Iterator[Finding]:
    """§5's closing requirement: the resource defining a class is confined by a
    blocking check that the scope's own gate runs."""
    reachable: set[str] = set()
    for scheduling_class in classes:
        aggregate = f"{scope}-check-{scheduling_class}"
        if repository.declares(aggregate):
            reachable.update(recipe.name for recipe in repository.graph.closure(aggregate))
    for scheduling_class in classes:
        qualifier = SCHEDULING_GUARDS.get(scheduling_class)
        if qualifier is None:
            continue
        guard = f"{scope}-check-{qualifier}"
        if guard not in reachable:
            yield Finding(
                "missing-scheduling-guard",
                f"`{scope}` declares the scheduling class `{scheduling_class}` but no class "
                f"aggregate runs `{guard}`; a class whose defining resource is reachable by "
                f"another route understates what its tests need",
            )


def _check_repository_aggregates(repository: _Repository) -> Iterator[Finding]:
    """§7's repository level: one aggregate per class over the scopes, and one
    complete aggregate over the classes."""
    graph = repository.graph
    missing = [
        scheduling_class
        for scheduling_class in repository.scheduling_classes
        if not repository.declares(f"check-{scheduling_class}")
    ]
    for scheduling_class in missing:
        yield Finding(
            "incomplete-aggregate",
            f"the repository declares the scheduling class `{scheduling_class}` but no "
            f"`check-{scheduling_class}` aggregate over the scopes that run it",
        )
    present = [
        scheduling_class
        for scheduling_class in repository.scheduling_classes
        if scheduling_class not in missing
    ]
    composed = {
        scheduling_class: set(graph.recipe(f"check-{scheduling_class}").dependencies)
        for scheduling_class in present
    }
    for scope in repository.scopes:
        classes = repository.scope_classes(scope)
        for scheduling_class in classes:
            aggregate = f"{scope}-check-{scheduling_class}"
            if (
                scheduling_class in composed
                and repository.declares(aggregate)
                and aggregate not in composed[scheduling_class]
            ):
                yield Finding(
                    "incomplete-aggregate",
                    f"`check-{scheduling_class}` does not compose `{aggregate}`, so it gates "
                    f"less than its name claims",
                )
        # A scope with no class of its own belongs to exactly one class aggregate:
        # omitted it is ungated, and composed twice it runs once per CI lane.
        if classes or not repository.declares(f"{scope}-check"):
            continue
        carriers = [
            scheduling_class
            for scheduling_class in present
            if f"{scope}-check" in composed[scheduling_class]
        ]
        if len(carriers) != 1:
            yield Finding(
                "incomplete-aggregate",
                f"`{scope}-check` declares no scheduling class and is composed by "
                f"{len(carriers)} class aggregate(s); exactly one must run it",
            )

    if not repository.declares("check"):
        yield Finding(
            "incomplete-aggregate",
            "the repository exposes no `check` aggregate over its scheduling classes",
        )
        return
    complete = set(graph.recipe("check").dependencies)
    for scheduling_class in repository.scheduling_classes:
        aggregate = f"check-{scheduling_class}"
        if repository.declares(aggregate) and aggregate not in complete:
            yield Finding(
                "incomplete-aggregate",
                f"`check` does not compose `{aggregate}`, so the complete merge gate omits "
                f"the `{scheduling_class}` class",
            )

    owners: dict[str, set[str]] = {}
    for scheduling_class in repository.scheduling_classes:
        aggregate = f"check-{scheduling_class}"
        if repository.declares(aggregate):
            owners[scheduling_class] = set(graph.resolve(aggregate).execution_owners)
    for first, second in _pairs(sorted(owners)):
        shared = owners[first] & owners[second]
        if shared:
            yield Finding(
                "overlapping-class-aggregates",
                f"`check-{first}` and `check-{second}` both run {', '.join(sorted(shared))}; "
                f"the class aggregates run as separate jobs, so a shared owner runs twice",
            )


def _pairs(values: Sequence[str]) -> Iterator[tuple[str, str]]:
    for index, first in enumerate(values):
        for second in values[index + 1 :]:
            yield (first, second)


def _check_runtime(repository: _Repository) -> Iterator[Finding]:
    """§6's declared runtime class, and the derivation an aggregate cannot
    understate."""
    for recipe in repository.public:
        declared = [
            value.removeprefix("runtime:")
            for value in recipe.metadata
            if value.startswith("runtime:")
        ]
        unknown = [value for value in declared if value not in RUNTIME_CLASSES]
        if unknown:
            yield Finding(
                "unknown-runtime-class",
                f"`{recipe.name}` declares the runtime class {', '.join(unknown)}; a runtime "
                f"class is one of {', '.join(RUNTIME_CLASSES)}",
            )
        elif not declared and recipe.role == "execution":
            yield Finding(
                "missing-runtime-class",
                f"`{recipe.name}` declares no runtime class; a reader cannot tell what running "
                f"it costs without running it",
            )
        if len(declared) > 1:
            yield Finding(
                "ambiguous-runtime-class",
                f"`{recipe.name}` declares {len(declared)} runtime classes "
                f"({', '.join(declared)}); a command costs one thing",
            )
        effective = repository.graph.resolve(recipe.name).understated_runtime_class
        if effective is not None:
            yield Finding(
                "understated-runtime-class",
                f"`{recipe.name}` declares {', '.join(sorted(recipe.declared_runtime_classes))} "
                f"but its closure is `{effective}`; a prerequisite costs what it costs",
            )


def _runner_config(module_dir: Path) -> _RunnerConfig | None:
    packaging = module_dir / "pyproject.toml"
    if not packaging.is_file():
        return None
    try:
        parsed: dict[str, Any] = tomllib.loads(packaging.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError:
        return None
    settings: dict[str, Any] = parsed
    for key in ("tool", "pytest", "ini_options"):
        nested: Any = settings.get(key)
        if not isinstance(nested, dict):
            return None
        settings = nested
    markers: Any = settings.get("markers", [])
    testpaths: Any = settings.get("testpaths", [])
    return _RunnerConfig(
        markers=tuple(str(marker) for marker in markers),
        addopts=str(settings.get("addopts", "")),
        testpaths=tuple(str(path) for path in testpaths),
    )


def _check_runner_config(repository: _Repository) -> Iterator[Finding]:
    """§5's mechanical enforcement, in the one place the runner reads it."""
    for scope in repository.scopes:
        classes = repository.scope_classes(scope)
        if not classes:
            continue
        module_dir = repository.module_dir(scope)
        if module_dir is None or not module_dir.is_dir():
            yield Finding(
                "unresolvable-scope-directory",
                f"`{scope}` runs tests but the file declares no directory for it; a scope "
                f"outside `languages/` names its path in an assignment called `{scope}`",
            )
            continue
        config = _runner_config(module_dir)
        if config is None:
            yield Finding(
                "missing-runner-configuration",
                f"`{scope}` declares a scheduling partition but {module_dir.name} holds no "
                f"readable test-runner configuration",
            )
            continue
        declared = {marker.split(":", 1)[0].strip() for marker in config.markers}
        for scheduling_class in classes:
            if scheduling_class not in declared:
                yield Finding(
                    "missing-marker-catalog",
                    f"`{scope}` selects the scheduling class `{scheduling_class}` but its "
                    f"runner catalog does not declare it",
                )
        if "--strict-markers" not in config.addopts:
            yield Finding(
                "permissive-markers",
                f"`{scope}`'s runner does not enable --strict-markers, so a misspelled "
                f"scheduling class silently selects nothing",
            )


def _test_root(repository: _Repository, scope: str) -> Path | None:
    module_dir = repository.module_dir(scope)
    if module_dir is None or not module_dir.is_dir():
        return None
    config = _runner_config(module_dir)
    if config is None or len(config.testpaths) != 1:
        return None
    return module_dir / config.testpaths[0]


def _check_layout(repository: _Repository) -> Iterator[Finding]:
    """§3's six surfaces and §4's closed test root, for every language scope."""
    for scope in repository.language_scopes:
        test_root = _test_root(repository, scope)
        if test_root is None or not test_root.is_dir():
            yield Finding(
                "ambiguous-test-root",
                f"`{scope}` declares no single test root, so the closed-entry rule has "
                f"nothing to apply to",
            )
            continue
        for qualifier, directory in SURFACES.items():
            if not (test_root / directory).is_dir():
                yield Finding(
                    "missing-surface-directory",
                    f"`{scope}` has no `{directory}/` under {test_root.name}/; every language "
                    f"scope provides all six primary semantic surfaces",
                )
            recipe_name = f"{scope}-test-{qualifier}"
            if not repository.declares(recipe_name):
                yield Finding(
                    "missing-surface-recipe",
                    f"`{scope}` exposes no `{recipe_name}` command for its {directory}/ surface",
                )
                continue
            yield from _check_surface_selection(repository, recipe_name, directory)
        for entry in sorted(test_root.iterdir()):
            if entry.name.startswith((".", "__")):
                continue
            if entry.is_dir() and entry.name in (*SURFACES.values(), SUPPORT_DIRECTORY):
                continue
            if entry.is_file() and entry.name in RUNNER_ROOT_FILES:
                continue
            yield Finding(
                "unexpected-test-root-entry",
                f"`{scope}` holds `{entry.name}` at the root of {test_root.name}/; the root "
                f"holds the surface directories, {SUPPORT_DIRECTORY}/, and the files the "
                f"runner requires",
            )


def _check_surface_selection(
    repository: _Repository, recipe_name: str, directory: str
) -> Iterator[Finding]:
    recipe = repository.graph.recipe(recipe_name)
    segments = {
        segment
        for line in recipe.body
        for token in repository.graph.expand(line).split()
        for segment in token.split("/")
    }
    selected = segments & set(SURFACES.values())
    if selected != {directory}:
        yield Finding(
            "surface-recipe-selection",
            f"`{recipe_name}` selects {', '.join(sorted(selected)) or 'no surface'} rather "
            f"than exactly {directory}/",
        )


def _jobs(workflow: Mapping[str, Any]) -> list[_Job]:
    jobs: list[_Job] = []
    declared: Any = workflow.get("jobs", {})
    if not isinstance(declared, dict):
        return jobs
    entries: dict[str, Any] = declared
    for identifier, definition in entries.items():
        commands: list[str] = []
        steps: Any = definition.get("steps", []) if isinstance(definition, dict) else []
        if isinstance(steps, list):
            listed: list[Any] = steps
            commands = [
                str(step["run"]) for step in listed if isinstance(step, dict) and "run" in step
            ]
        invoked = [
            match.group("recipe")
            for command in commands
            for match in _JUST_INVOCATION_RE.finditer(command)
        ]
        jobs.append(
            _Job(identifier=str(identifier), invoked=tuple(invoked), commands=tuple(commands))
        )
    return jobs


def _blocking_owners(repository: _Repository, name: str) -> set[str]:
    """Every command running *name* executes that carries a verdict. A
    non-blocking one is no gate, so CI neither has to cover it nor owns it twice
    by running it."""
    return {
        owner
        for owner in repository.graph.resolve(name).execution_owners
        if repository.graph.recipe(owner).operation in BLOCKING_OPERATIONS
    }


def _workflow_jobs(root: Path) -> list[_Job] | None:
    """Every job the CI workflow declares, or ``None`` when it declares no
    workflow at all."""
    workflow_path = root / CI_WORKFLOW
    if not workflow_path.is_file():
        return None
    parsed: Any = yaml.safe_load(workflow_path.read_text(encoding="utf-8"))
    return _jobs(parsed) if isinstance(parsed, dict) else []


def _check_ci(repository: _Repository) -> Iterator[Finding]:
    """§9: the same interface as local verification, covering the same graph."""
    jobs = _workflow_jobs(repository.root)
    if jobs is None:
        yield Finding(
            "missing-ci-workflow",
            f"{CI_WORKFLOW} does not exist, so no job list can be compared with the graph",
        )
        return

    covered: set[str] = set()
    ownership: dict[str, set[str]] = {}
    for job in jobs:
        for command in job.commands:
            performed = _runner_operation(command)
            if performed is not None:
                yield Finding(
                    "ci-embedded-gate",
                    f"job `{job.identifier}` runs `{command.strip()}`, embedding a "
                    f"`{performed}` gate a canonical command already owns",
                )
        unknown = [name for name in job.invoked if not repository.declares(name)]
        for name in unknown:
            yield Finding(
                "ci-unknown-recipe",
                f"job `{job.identifier}` invokes `just {name}`, which the graph does not declare",
            )
        resolved = [name for name in job.invoked if repository.declares(name)]
        if resolved and job.identifier not in resolved:
            yield Finding(
                "ci-job-name-mismatch",
                f"job `{job.identifier}` runs {', '.join(sorted(set(resolved)))}; a job's "
                f"identifier matches the command it executes",
            )
        elif not resolved and repository.declares(job.identifier):
            yield Finding(
                "ci-missing-invocation",
                f"job `{job.identifier}` names a command but does not invoke it; the primary "
                f"verification step invokes that command directly",
            )
        owners = {owner for name in resolved for owner in _blocking_owners(repository, name)}
        if owners:
            ownership[job.identifier] = owners
        covered |= owners

    for first, second in _pairs(sorted(ownership)):
        shared = ownership[first] & ownership[second]
        if shared:
            yield Finding(
                "ci-duplicate-ownership",
                f"jobs `{first}` and `{second}` both run {', '.join(sorted(shared))}; a matrix "
                f"expands one job, and anything else is a gate owned twice",
            )

    if not repository.declares("check"):
        return
    for missing in sorted(_blocking_owners(repository, "check") - covered):
        yield Finding(
            "ci-uncovered-gate",
            f"no job runs `{missing}`; the union of jobs covers the complete required check "
            f"graph even when CI parallelizes it",
        )


def _operational_maps(repository: _Repository) -> dict[str | None, Path]:
    """Each operational map and the scope it speaks for. The repository's own map
    speaks for every scope, so a scoped job is answerable to two of them."""
    maps: dict[str | None, Path] = {None: repository.root / OPERATIONAL_MAP}
    for scope in repository.language_scopes:
        directory = repository.module_dir(scope)
        if directory is not None:
            maps[scope] = directory / OPERATIONAL_MAP
    return maps


def _check_documentation(repository: _Repository) -> Iterator[Finding]:
    """§8's documentation drift, over the third representation of the gates."""
    cited: dict[str | None, frozenset[str]] = {}
    for scope, path in _operational_maps(repository).items():
        subject = "the repository" if scope is None else f"`{scope}`"
        if not path.is_file():
            yield Finding(
                "missing-operational-map",
                f"{subject} has no {path.relative_to(repository.root)}; a scope whose commands "
                f"nothing maps is navigable only by reading the orchestrator's own file",
            )
            continue
        spans = frozenset(_CODE_SPAN_RE.findall(path.read_text(encoding="utf-8")))
        cited[scope] = spans
        for span in sorted(spans):
            match = _CITED_COMMAND_RE.match(span)
            if match is None or repository.declares(match.group("recipe")):
                continue
            yield Finding(
                "doc-unknown-command",
                f"{path.relative_to(repository.root)} cites `{span}`, which the graph does "
                f"not declare",
            )

    jobs = _workflow_jobs(repository.root)
    if jobs is None:
        return
    for job in jobs:
        if not repository.declares(job.identifier):
            continue
        scope = repository.graph.recipe(job.identifier).scope
        for audience in dict.fromkeys((None, scope)):
            spans = cited.get(audience)
            if spans is None or job.identifier in spans:
                continue
            path = _operational_maps(repository)[audience]
            yield Finding(
                "doc-uncovered-ci-job",
                f"{path.relative_to(repository.root)} does not name the CI job "
                f"`{job.identifier}`; a map that omits a lane understates what gates a merge",
            )


_RULES = (
    _check_names,
    _check_order,
    _check_roles,
    _check_scheduling,
    _check_runtime,
    _check_runner_config,
    _check_layout,
    _check_ci,
    _check_documentation,
)


def audit(root: Path, graph: GateGraph) -> list[Finding]:
    """Every way *graph* and the repository at *root* break the contract.

    *graph* is passed rather than loaded so a caller can judge a candidate
    justfile against a real repository.
    """
    repository = _load_repository(root, graph)
    return [finding for rule in _RULES for finding in rule(repository)]


def _usage() -> str:
    return "usage: python -m reference_harness.check_gates <repository-root>"


def main(argv: list[str]) -> int:
    """Audit the repository rooted at the single argument.

    Exit codes: 0 — the graph conforms; 1 — it breaks the contract, or could not
    be resolved; 2 — usage error.
    """
    if len(argv) != 1:
        print(_usage(), file=sys.stderr)
        return 2
    root = Path(argv[0]).resolve()
    if not root.is_dir():
        print(f"not a directory: {root}", file=sys.stderr)
        return 2

    try:
        graph = load_graph(root)
        findings = audit(root, graph)
    except (GateGraphError, OSError, ValueError, yaml.YAMLError) as exc:
        print(f"gate check FAILED: {exc}", file=sys.stderr)
        return 1

    if findings:
        print(
            f"gate check FAILED ({len(findings)} problem(s)): the command graph at "
            f"{graph.source} breaks core/spec/language-testing.md",
            file=sys.stderr,
        )
        for finding in findings:
            print(f"  - {finding}", file=sys.stderr)
        return 1

    public = sum(1 for recipe in graph.recipes if not recipe.private)
    print(f"gate check OK: {public} public command(s) conform")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
