"""Fail when the repository's verification-command graph breaks the language
testing contract::

    uv run python -m reference_harness.check_gates <repository-root>

`core/spec/language-testing.md` fixes the command grammar, the operation
vocabulary, the two command roles, the scheduling partition, the runtime
declaration, the test-root structure, the declaration order, and the CI
contract. Until something reads the graph and fails on a breach, every one of
those rules is a convention that holds only while each author remembers it. This
is the blocking check §8 requires over the graph.

Every rule is decided from the orchestrator's own dump, from the runner
configuration and test roots the graph itself locates, from the CI workflow, and
from the documents that describe the gates. Nothing is restated here that one of
those already states: a second description of the gates is what §8 forbids, and a
checker that carried its own copy of the recipe list would be one.
"""

from __future__ import annotations

import re
import shlex
import sys
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

import yaml

from reference_harness import ci_workflow, runner_config
from reference_harness.diagnostics import Diagnostic, report_failures
from reference_harness.gate_graph import (
    BLOCKING_OPERATIONS,
    OPERATIONS,
    RUNTIME_CLASSES,
    GateGraph,
    GateGraphError,
    Recipe,
    load_graph,
)
from reference_harness.markdown_read import code_spans

__all__ = [
    "AGENT_GUIDANCE",
    "CI_WORKFLOW",
    "OPERATIONAL_MAP",
    "SUPPORT_DIRECTORY",
    "SURFACES",
    "main",
]

_TOOLING_SCOPES: tuple[str, ...] = ("core", "harness")
"""The scopes that validate a shared artifact or maintain the repository's own
tooling. Every other scope is a language, discovered under ``languages/``."""

SURFACES: Mapping[str, str] = {
    "unit": "unit",
    "compatibility": "compatibility",
    "api": "api",
    "dialect": "dialect",
    "provider-contract": "provider_contract",
    "distribution": "distribution",
}
"""The six primary semantic surfaces every language scope provides, as the
focused command's qualifier mapped to the directory holding that surface. Both
spellings come from the contract's §3 table rather than from any ecosystem's
naming convention."""

SUPPORT_DIRECTORY = "_support"
"""The one non-surface directory a language scope's test root may hold."""

_SCHEDULING_GUARDS: Mapping[str, str | None] = {"db": "database-access", "dbfree": None}
"""What confines each scheduling class's defining resource, by class.

A class is honest only while the resource that defines it is unreachable by any
other route, and §5 makes that restriction a blocking check of its own. Which
resource a class is about is a fact about the class, not about the graph, so it
is named here rather than derived: `db` is defined by live database access, and
the check confining it is `<scope>-check-database-access`. `dbfree` maps to
``None`` because it is defined by the *absence* of that resource, and an absence
cannot be confined.

The mapping is closed on purpose. A class absent from it is one whose defining
resource this command cannot name, so it is reported rather than passed over —
the alternative is a class that quietly owes no guard at all, which is the state
§5 exists to prevent. Where a guard itself looks — a fixture name, a set of
seams — stays in that guard; this command only requires that one exists and that
a class aggregate runs it."""

CI_WORKFLOW = Path(".github/workflows/ci.yml")
"""The workflow whose jobs must cover the required repository check graph."""

OPERATIONAL_MAP = "TESTING.md"
"""The operational map, at the repository root and in every language scope.

The graph, the maps, the language specs, the agent guidance, and the CI job list
all describe which commands gate this repository. Three pairs are compared here,
and one is deliberately not:

- graph → documents: every command a map, a language spec, or an agent-guidance
  document cites must resolve (`doc-unknown-command`);
- CI → maps: every job must be named by the maps answerable for it
  (`doc-uncovered-ci-job`);
- maps → CI: every job a map's CI table names must exist
  (`doc-unknown-ci-job`).

Documents → graph *completeness* is not compared. A map is not required to cite
every command in its scope: `just --list` is the catalog, the contract calls
these documents concise, and requiring completeness would turn a scope's map
into a second listing — which §8 forbids. So an added command needs no
documentation edit, while a renamed or removed one fails every document still
naming it."""

AGENT_GUIDANCE = "AGENTS.md"
"""The agent guidance, at the repository root and in every language scope.

It tells an agent which command to run, so a name it cites is answerable to the
graph exactly as a map's or a language spec's is — and naming commands there is
safe only while a rename fails on it. Nothing requires the document to exist:
guidance is not a gate, so a scope without one cites nothing."""

_CI_SECTION_TITLE = "Continuous integration"

_RECIPE_LINE_RE = re.compile(r"^(?P<name>[A-Za-z_][A-Za-z0-9_-]*)[^:=\n]*:(?!=)", re.MULTILINE)
_HEADING_RE = re.compile(r"^(?P<hashes>#{1,6})[ \t]+(?P<title>.+?)[ \t]*$", re.MULTILINE)
# A code span citing a command: the orchestrator, one recipe name, and whatever
# arguments follow. A span holding a placeholder rather than a name — the
# `<surface>` of a family of commands — matches nothing and cites nothing.
_CITED_COMMAND_RE = re.compile(r"^just (?P<recipe>[a-z][a-z0-9-]*)(?:\s.*)?$")
_IDENTIFIER_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_-]*")

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


def _module_dir(
    root: Path, language_scopes: Sequence[str], graph: GateGraph, scope: str
) -> Path | None:
    """Where *scope*'s module lives, or ``None`` when the file declares no path
    for it.

    A language scope is a directory under ``languages/`` by construction — that
    is where it was discovered. Any other scope names its own path in an
    assignment named after the scope, which is the file's own declaration rather
    than a convention restated here.
    """
    if scope in language_scopes:
        return root / "languages" / scope
    location = graph.assignments.get(scope)
    return None if location is None else root / location


@dataclass(frozen=True)
class _Repository:
    """The graph together with what the repository layout says about it."""

    root: Path
    graph: GateGraph
    public: tuple[Recipe, ...]
    language_scopes: tuple[str, ...]
    scheduling_classes: tuple[str, ...]
    runners: Mapping[str, runner_config.RunnerConfiguration | None]
    jobs: tuple[ci_workflow.Job, ...] | None

    @property
    def scopes(self) -> tuple[str, ...]:
        return _TOOLING_SCOPES + self.language_scopes

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
        return _module_dir(self.root, self.language_scopes, self.graph, scope)

    def language_dir(self, scope: str) -> Path:
        """Where a language scope lives, which its discovery already fixed."""
        return self.root / "languages" / scope

    def execution_owners(self, name: str) -> tuple[str, ...]:
        """Every command running *name* executes, in run order."""
        return self.graph.resolve(name).execution_owners

    def blocking_owners(self, name: str) -> set[str]:
        """Those execution owners of *name* that carry a verdict. A non-blocking
        one is no gate, so CI neither has to cover it nor owns it twice by
        running it."""
        return {
            owner
            for owner in self.execution_owners(name)
            if self.graph.recipe(owner).operation in BLOCKING_OPERATIONS
        }

    def relative(self, path: Path) -> Path:
        return path.relative_to(self.root)


def _runner_operation(command: str) -> str | None:
    for pattern, operation in _RUNNER_OPERATIONS:
        if pattern.search(command):
            return operation
    return None


def _shell_tokens(command: str) -> list[str]:
    """*command* split the way a shell would, so a quoted selection expression
    stays one argument. A command that does not lex falls back to whitespace."""
    try:
        return shlex.split(command)
    except ValueError:
        return command.split()


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
    runners: dict[str, runner_config.RunnerConfiguration | None] = {}
    for scope in _TOOLING_SCOPES + language_scopes:
        directory = _module_dir(root, language_scopes, graph, scope)
        runners[scope] = (
            runner_config.read(directory) if directory is not None and directory.is_dir() else None
        )
    jobs = ci_workflow.jobs(root / CI_WORKFLOW)
    return _Repository(
        root=root,
        graph=graph,
        public=public,
        language_scopes=language_scopes,
        scheduling_classes=tuple(sorted(classes)),
        runners=runners,
        jobs=None if jobs is None else tuple(jobs),
    )


def _check_names(repository: _Repository) -> Iterator[Diagnostic]:
    """§1's grammar and §2's closed vocabulary, over public commands."""
    known = set(repository.scopes)
    for recipe in repository.public:
        if recipe.operation not in OPERATIONS:
            yield Diagnostic(
                "non-canonical-operation",
                f"`{recipe.name}` performs the operation `{recipe.operation}`, which is "
                f"outside the closed vocabulary ({', '.join(OPERATIONS)})",
            )
        if recipe.scope is not None and recipe.scope not in known:
            yield Diagnostic(
                "unknown-scope",
                f"`{recipe.name}` names the scope `{recipe.scope}`; a scope is one of "
                f"{', '.join(sorted(known))}",
            )


def _section(recipe: Recipe, repository: _Repository) -> int | None:
    """Which top-level section of the file *recipe* belongs in, or ``None`` when
    its scope is not one the file has a section for."""
    if recipe.scope is None:
        return 1 if recipe.operation in BLOCKING_OPERATIONS else 2
    if recipe.scope in _TOOLING_SCOPES:
        return 3 + _TOOLING_SCOPES.index(recipe.scope)
    if recipe.scope in repository.language_scopes:
        return 3 + len(_TOOLING_SCOPES) + repository.language_scopes.index(recipe.scope)
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


def _check_order(repository: _Repository) -> Iterator[Diagnostic]:
    """§7's declaration order, top-level sections first and each section's own
    progression second."""
    previous: tuple[Recipe, int, int] | None = None
    for recipe in _source_order(repository):
        section = _section(recipe, repository)
        if section is None:
            continue
        rank = _within_section(recipe)
        if previous is not None:
            earlier, earlier_section, earlier_rank = previous
            if section < earlier_section:
                yield Diagnostic(
                    "section-order",
                    f"`{recipe.name}` is declared after `{earlier.name}`, which belongs to a "
                    f"later section: the file runs the repository-wide blocking commands, the "
                    f"repository-wide non-blocking ones, then one section per scope",
                )
            elif section == earlier_section and rank < earlier_rank:
                yield Diagnostic(
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


def _check_roles(repository: _Repository) -> Iterator[Diagnostic]:
    """§7's two roles, and the limit on what one execution body may do."""
    dependency_only = set(_required_aggregates(repository))
    for recipe in repository.public:
        if not recipe.body and not recipe.dependencies:
            yield Diagnostic(
                "composes-nothing",
                f"`{recipe.name}` has no command body and no dependency; an aggregate that "
                f"composes nothing gates nothing",
            )
        if recipe.body and recipe.name in dependency_only:
            yield Diagnostic(
                "aggregate-with-body",
                f"`{recipe.name}` composes other commands and carries a command body; an "
                f"aggregate cannot be composed without re-running that body",
            )
        if recipe.role != "execution":
            continue
        for line in recipe.body:
            performed = _runner_operation(line)
            if performed is not None and performed != recipe.operation:
                yield Diagnostic(
                    "inlined-operation",
                    f"`{recipe.name}` performs `{performed}` in `{line.strip()}`, which is an "
                    f"operation its name does not declare",
                )
        if _is_scheduling_test(recipe):
            invocations = [line for line in recipe.body if _runner_operation(line) == "test"]
            if len(invocations) != 1:
                yield Diagnostic(
                    "multiple-test-invocations",
                    f"`{recipe.name}` owns a scheduling class and makes {len(invocations)} "
                    f"test-runner invocations; a class is one selection, run once",
                )


def _check_scheduling(repository: _Repository) -> Iterator[Diagnostic]:
    """§5's partition and §7's composition, read off the declarations rather than
    off the names."""
    graph = repository.graph
    for recipe in repository.public:
        declared = recipe.declared_scheduling_classes
        misplaced = [
            scheduling_class
            for scheduling_class in sorted(declared)
            if recipe.name != f"{recipe.scope}-test-{scheduling_class}"
        ]
        for scheduling_class in misplaced:
            owner = f"{recipe.scope}-test-{scheduling_class}"
            yield Diagnostic(
                "misplaced-scheduling-class",
                f"`{recipe.name}` declares the scheduling class `{scheduling_class}`; the "
                f"command owning that class's execution is `{owner}`",
            )
        if declared and not misplaced:
            yield from _check_class_selection(repository, recipe, declared)

    for recipe in repository.public:
        for dependency in recipe.dependencies:
            if _is_focused_test(graph.recipe(dependency)):
                yield Diagnostic(
                    "focused-test-in-aggregate",
                    f"`{recipe.name}` depends on the focused selector `{dependency}`, which "
                    f"cuts across the scheduling partition and would be selected twice",
                )

    for scope in repository.scopes:
        classes = repository.scope_classes(scope)
        if scope in repository.language_scopes and not repository.declares(f"{scope}-check"):
            yield Diagnostic(
                "missing-aggregate",
                f"`{scope}` exposes no `{scope}-check` aggregate; its language spec names one "
                f"complete verification command, and nothing else in the graph provides it",
            )
        for scheduling_class in classes:
            aggregate = f"{scope}-check-{scheduling_class}"
            if not repository.declares(aggregate):
                yield Diagnostic(
                    "missing-aggregate",
                    f"`{scope}` declares the scheduling class `{scheduling_class}` but exposes "
                    f"no `{aggregate}` aggregate for it",
                )
                continue
            reached = {recipe.name for recipe in graph.closure(aggregate)}
            owner = f"{scope}-test-{scheduling_class}"
            if owner not in reached:
                yield Diagnostic(
                    "incomplete-aggregate",
                    f"`{aggregate}` does not compose `{owner}`, so the class it names is not "
                    f"what it runs",
                )
            for other in classes:
                foreign = f"{scope}-test-{other}"
                if other != scheduling_class and foreign in reached:
                    yield Diagnostic(
                        "foreign-test-in-aggregate",
                        f"`{aggregate}` composes `{foreign}`, which belongs to the "
                        f"`{other}` class; class selections must stay disjoint",
                    )
        yield from _check_scheduling_guard(repository, scope, classes)

    yield from _check_repository_aggregates(repository)


def _selected_scheduling_classes(repository: _Repository, recipe: Recipe) -> frozenset[str] | None:
    """Which scheduling classes *recipe*'s test invocations select, or ``None``
    when the scope's runner configuration cannot be read.

    The selection lives in the argument of the runner's own selection flag, so
    only that argument is read: a path, an option, or a coverage threshold that
    happens to spell a class name is not a selection. A body preserves its
    source spelling, so the file's own assignments are applied first.
    """
    config = None if recipe.scope is None else repository.runners.get(recipe.scope)
    if config is None:
        return None
    known = set(repository.scheduling_classes)
    selected: set[str] = set()
    for line in recipe.body:
        if _runner_operation(line) != "test":
            continue
        tokens = _shell_tokens(repository.graph.expand(line))
        for flag, argument in zip(tokens, tokens[1:], strict=False):
            if flag == config.profile.selection_flag:
                selected |= {word for word in _IDENTIFIER_RE.findall(argument) if word in known}
    return frozenset(selected)


def _check_class_selection(
    repository: _Repository, recipe: Recipe, declared: frozenset[str]
) -> Iterator[Diagnostic]:
    """§5's disjoint and collectively complete selections, at the one command
    that owns a class: what it runs must be the class it declares.

    Counting a class owner's test-runner invocations says the selection is made
    once; it says nothing about which selection. A command naming one class and
    selecting another leaves its own class unrun and another class run twice,
    and both aggregates still pass.
    """
    selected = _selected_scheduling_classes(repository, recipe)
    if selected is None or selected == declared:
        return
    yield Diagnostic(
        "scheduling-recipe-selection",
        f"`{recipe.name}` selects {', '.join(sorted(selected)) or 'no scheduling class'} "
        f"rather than exactly {', '.join(sorted(declared))}; the command owning a class runs "
        f"that class's tests and no others",
    )


def _check_scheduling_guard(
    repository: _Repository, scope: str, classes: Sequence[str]
) -> Iterator[Diagnostic]:
    """§5's closing requirement: the resource defining a class is confined by a
    blocking check that the scope's own gate runs."""
    reachable: set[str] = set()
    for scheduling_class in classes:
        aggregate = f"{scope}-check-{scheduling_class}"
        if repository.declares(aggregate):
            reachable.update(recipe.name for recipe in repository.graph.closure(aggregate))
    for scheduling_class in classes:
        if scheduling_class not in _SCHEDULING_GUARDS:
            yield Diagnostic(
                "unknown-scheduling-class",
                f"`{scope}` declares the scheduling class `{scheduling_class}`, which this "
                f"check cannot name a defining resource for; §5 requires every class's "
                f"resource to be confined by a blocking check, and which resource a class is "
                f"about is not readable from the graph",
            )
            continue
        qualifier = _SCHEDULING_GUARDS[scheduling_class]
        if qualifier is None:
            continue
        guard = f"{scope}-check-{qualifier}"
        if guard not in reachable:
            yield Diagnostic(
                "missing-scheduling-guard",
                f"`{scope}` declares the scheduling class `{scheduling_class}` but no class "
                f"aggregate runs `{guard}`; a class whose defining resource is reachable by "
                f"another route understates what its tests need",
            )


def _check_repository_aggregates(repository: _Repository) -> Iterator[Diagnostic]:
    """§7's repository level: one aggregate per class over the scopes, and one
    complete aggregate over the classes."""
    graph = repository.graph
    missing = [
        scheduling_class
        for scheduling_class in repository.scheduling_classes
        if not repository.declares(f"check-{scheduling_class}")
    ]
    for scheduling_class in missing:
        yield Diagnostic(
            "missing-aggregate",
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
                yield Diagnostic(
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
            yield Diagnostic(
                "ambiguous-class-ownership",
                f"`{scope}-check` declares no scheduling class and is composed by "
                f"{len(carriers)} class aggregate(s); exactly one must run it",
            )

    if not repository.declares("check"):
        yield Diagnostic(
            "missing-aggregate",
            "the repository exposes no `check` aggregate over its scheduling classes",
        )
        return
    complete = set(graph.recipe("check").dependencies)
    for scheduling_class in repository.scheduling_classes:
        aggregate = f"check-{scheduling_class}"
        if repository.declares(aggregate) and aggregate not in complete:
            yield Diagnostic(
                "incomplete-aggregate",
                f"`check` does not compose `{aggregate}`, so the complete merge gate omits "
                f"the `{scheduling_class}` class",
            )

    owners: dict[str, set[str]] = {}
    for scheduling_class in repository.scheduling_classes:
        aggregate = f"check-{scheduling_class}"
        if repository.declares(aggregate):
            owners[scheduling_class] = set(repository.execution_owners(aggregate))
    for first, second in _pairs(sorted(owners)):
        shared = owners[first] & owners[second]
        if shared:
            yield Diagnostic(
                "overlapping-class-aggregates",
                f"`check-{first}` and `check-{second}` both run {', '.join(sorted(shared))}; "
                f"the class aggregates run as separate jobs, so a shared owner runs twice",
            )


def _check_gate_ownership(repository: _Repository) -> Iterator[Diagnostic]:
    """§5's "every logical gate has exactly one execution owner inside a complete
    aggregate", read from the complete aggregate outwards.

    The class aggregates decide which gates run *together*; only the repository's
    own complete aggregate decides which gates run *at all*. A blocking command
    it never reaches is a verdict nobody asks for, and every other rule here
    still passes over it.

    Two kinds of command are legitimately outside it, both by the contract's own
    reckoning: a non-blocking operation belongs to no gate (§2, §7), and a
    focused selector cuts across the scheduling partition, so §3 requires it to
    be no aggregate's dependency.
    """
    if not repository.declares("check"):
        return
    owned = set(repository.execution_owners("check"))
    for recipe in repository.public:
        if recipe.role != "execution" or recipe.name in owned:
            continue
        if recipe.operation not in BLOCKING_OPERATIONS or _is_focused_test(recipe):
            continue
        yield Diagnostic(
            "unowned-gate",
            f"`{recipe.name}` performs a blocking `{recipe.operation}` that `check` never runs; "
            f"a gate outside the complete aggregate passes only while someone remembers to "
            f"invoke it",
        )


def _pairs(values: Sequence[str]) -> Iterator[tuple[str, str]]:
    for index, first in enumerate(values):
        for second in values[index + 1 :]:
            yield (first, second)


def _check_runtime(repository: _Repository) -> Iterator[Diagnostic]:
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
            yield Diagnostic(
                "unknown-runtime-class",
                f"`{recipe.name}` declares the runtime class {', '.join(unknown)}; a runtime "
                f"class is one of {', '.join(RUNTIME_CLASSES)}",
            )
        elif not declared and recipe.role == "execution":
            yield Diagnostic(
                "missing-runtime-class",
                f"`{recipe.name}` declares no runtime class; a reader cannot tell what running "
                f"it costs without running it",
            )
        if len(declared) > 1:
            yield Diagnostic(
                "ambiguous-runtime-class",
                f"`{recipe.name}` declares {len(declared)} runtime classes "
                f"({', '.join(declared)}); a command costs one thing",
            )
        effective = repository.graph.resolve(recipe.name).understated_runtime_class
        if effective is not None:
            yield Diagnostic(
                "understated-runtime-class",
                f"`{recipe.name}` declares {', '.join(sorted(recipe.declared_runtime_classes))} "
                f"but its closure is `{effective}`; a prerequisite costs what it costs",
            )


def _check_runner_config(repository: _Repository) -> Iterator[Diagnostic]:
    """§5's mechanical enforcement, in the one place the runner reads it."""
    for scope in repository.scopes:
        classes = repository.scope_classes(scope)
        if not classes:
            continue
        module_dir = repository.module_dir(scope)
        if module_dir is None or not module_dir.is_dir():
            yield Diagnostic(
                "unresolvable-scope-directory",
                f"`{scope}` runs tests but the file declares no directory for it; a scope "
                f"outside `languages/` names its path in an assignment called `{scope}`",
            )
            continue
        config = repository.runners.get(scope)
        if config is None:
            known = ", ".join(profile.runner for profile in runner_config.PROFILES)
            yield Diagnostic(
                "missing-runner-configuration",
                f"`{scope}` declares a scheduling partition but {module_dir.name} holds no "
                f"readable configuration for any runner this check reads ({known})",
            )
            continue
        for scheduling_class in classes:
            if scheduling_class not in config.catalog:
                yield Diagnostic(
                    "missing-marker-catalog",
                    f"`{scope}` selects the scheduling class `{scheduling_class}` but its "
                    f"runner catalog does not declare it",
                )
        if not config.rejects_unknown_classes:
            yield Diagnostic(
                "permissive-markers",
                f"`{scope}`'s runner does not enable {config.profile.strictness_flag}, so a "
                f"misspelled scheduling class silently selects nothing",
            )


def _test_root(repository: _Repository, scope: str) -> Path | None:
    config = repository.runners.get(scope)
    if config is None or len(config.test_paths) != 1:
        return None
    return repository.language_dir(scope) / config.test_paths[0]


def _check_layout(repository: _Repository) -> Iterator[Diagnostic]:
    """§3's six surfaces and §4's closed test root, for every language scope."""
    for scope in repository.language_scopes:
        test_root = _test_root(repository, scope)
        config = repository.runners.get(scope)
        if test_root is None or config is None or not test_root.is_dir():
            yield Diagnostic(
                "ambiguous-test-root",
                f"`{scope}` declares no single test root, so the closed-entry rule has "
                f"nothing to apply to",
            )
            continue
        for qualifier, directory in SURFACES.items():
            if not (test_root / directory).is_dir():
                yield Diagnostic(
                    "missing-surface-directory",
                    f"`{scope}` has no `{directory}/` under {test_root.name}/; every language "
                    f"scope provides all six primary semantic surfaces",
                )
            recipe_name = f"{scope}-test-{qualifier}"
            if not repository.declares(recipe_name):
                yield Diagnostic(
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
            if entry.is_file() and entry.name in config.profile.root_files:
                continue
            yield Diagnostic(
                "unexpected-test-root-entry",
                f"`{scope}` holds `{entry.name}` at the root of {test_root.name}/; the root "
                f"holds the surface directories, {SUPPORT_DIRECTORY}/, and the files "
                f"{config.profile.runner} requires",
            )


def _check_surface_selection(
    repository: _Repository, recipe_name: str, directory: str
) -> Iterator[Diagnostic]:
    recipe = repository.graph.recipe(recipe_name)
    segments = {
        segment
        for line in recipe.body
        for token in repository.graph.expand(line).split()
        for segment in token.split("/")
    }
    selected = segments & set(SURFACES.values())
    if selected != {directory}:
        yield Diagnostic(
            "surface-recipe-selection",
            f"`{recipe_name}` selects {', '.join(sorted(selected)) or 'no surface'} rather "
            f"than exactly {directory}/",
        )


def _check_ci(repository: _Repository) -> Iterator[Diagnostic]:
    """§9: the same interface as local verification, covering the same graph."""
    if repository.jobs is None:
        yield Diagnostic(
            "missing-ci-workflow",
            f"{CI_WORKFLOW} does not exist, so no job list can be compared with the graph",
        )
        return

    covered: set[str] = set()
    ownership: dict[str, set[str]] = {}
    for job in repository.jobs:
        for command in job.commands:
            performed = _runner_operation(command)
            if performed is not None:
                yield Diagnostic(
                    "ci-embedded-gate",
                    f"job `{job.identifier}` runs `{command.strip()}`, embedding a "
                    f"`{performed}` gate a canonical command already owns",
                )
        unknown = [name for name in job.invoked if not repository.declares(name)]
        for name in unknown:
            yield Diagnostic(
                "ci-unknown-recipe",
                f"job `{job.identifier}` invokes `just {name}`, which the graph does not declare",
            )
        resolved = [name for name in job.invoked if repository.declares(name)]
        if resolved and job.identifier not in resolved:
            yield Diagnostic(
                "ci-job-name-mismatch",
                f"job `{job.identifier}` runs {', '.join(sorted(set(resolved)))}; a job's "
                f"identifier matches the command it executes",
            )
        elif not resolved and repository.declares(job.identifier):
            yield Diagnostic(
                "ci-missing-invocation",
                f"job `{job.identifier}` names a command but does not invoke it; the primary "
                f"verification step invokes that command directly",
            )
        owners = {owner for name in resolved for owner in repository.blocking_owners(name)}
        if owners:
            ownership[job.identifier] = owners
        covered |= owners

    for first, second in _pairs(sorted(ownership)):
        shared = ownership[first] & ownership[second]
        if shared:
            yield Diagnostic(
                "ci-duplicate-ownership",
                f"jobs `{first}` and `{second}` both run {', '.join(sorted(shared))}; a matrix "
                f"expands one job, and anything else is a gate owned twice",
            )

    if not repository.declares("check"):
        return
    for missing in sorted(repository.blocking_owners("check") - covered):
        yield Diagnostic(
            "ci-uncovered-gate",
            f"no job runs `{missing}`; the union of jobs covers the complete required check "
            f"graph even when CI parallelizes it",
        )


def _operational_maps(repository: _Repository) -> dict[str | None, Path]:
    """Each operational map and the scope it speaks for. The repository's own map
    speaks for every scope, so a scoped job is answerable to two of them."""
    maps: dict[str | None, Path] = {None: repository.root / OPERATIONAL_MAP}
    for scope in repository.language_scopes:
        maps[scope] = repository.language_dir(scope) / OPERATIONAL_MAP
    return maps


def _language_specs(repository: _Repository) -> list[Path]:
    """Every language spec, which names its scope's aggregate commands
    normatively and is therefore answerable to the graph the same way a map is."""
    return [
        spec
        for scope in repository.language_scopes
        for spec in sorted((repository.language_dir(scope) / "spec").glob("*.md"))
    ]


def _agent_guidance(repository: _Repository) -> list[Path]:
    """Each agent-guidance document that exists, over the audiences the
    operational maps have."""
    candidates = [repository.root / AGENT_GUIDANCE] + [
        repository.language_dir(scope) / AGENT_GUIDANCE for scope in repository.language_scopes
    ]
    return [path for path in candidates if path.is_file()]


def _section_body(text: str, title: str) -> str:
    """The body of the section *title* opens, or empty when there is none."""
    headings = list(_HEADING_RE.finditer(text))
    wanted = title.casefold()
    for index, heading in enumerate(headings):
        if heading.group("title").strip().casefold() != wanted:
            continue
        level = len(heading.group("hashes"))
        end = len(text)
        for later in headings[index + 1 :]:
            if len(later.group("hashes")) <= level:
                end = later.start()
                break
        return text[heading.end() : end]
    return ""


def _named_ci_jobs(text: str) -> frozenset[str]:
    """Every job an operational map's CI table names, read from each row's first
    cell — the one column that identifies a lane rather than describing it."""
    named: set[str] = set()
    for line in _section_body(text, _CI_SECTION_TITLE).splitlines():
        stripped = line.strip()
        if not stripped.startswith("|"):
            continue
        named |= code_spans(stripped.strip("|").split("|")[0])
    return frozenset(named)


def _check_cited_commands(
    repository: _Repository, path: Path, spans: frozenset[str]
) -> Iterator[Diagnostic]:
    """Every command a document cites must resolve in the graph."""
    for span in sorted(spans):
        match = _CITED_COMMAND_RE.match(span)
        if match is None or repository.declares(match.group("recipe")):
            continue
        yield Diagnostic(
            "doc-unknown-command",
            f"{repository.relative(path)} cites `{span}`, which the graph does not declare",
        )


def _check_documentation(repository: _Repository) -> Iterator[Diagnostic]:
    """§8's documentation drift, over the representations of the gates that are
    neither the graph nor the CI workflow."""
    cited: dict[str | None, frozenset[str]] = {}
    maps = _operational_maps(repository)
    job_identifiers = (
        None if repository.jobs is None else {job.identifier for job in repository.jobs}
    )
    for scope, path in maps.items():
        subject = "the repository" if scope is None else f"`{scope}`"
        if not path.is_file():
            yield Diagnostic(
                "doc-missing-operational-map",
                f"{subject} has no {repository.relative(path)}; a scope whose commands nothing "
                f"maps is navigable only by reading the orchestrator's own file",
            )
            continue
        text = path.read_text(encoding="utf-8")
        cited[scope] = code_spans(text)
        yield from _check_cited_commands(repository, path, cited[scope])
        if job_identifiers is None:
            continue
        for name in sorted(_named_ci_jobs(text)):
            if repository.declares(name) and name not in job_identifiers:
                yield Diagnostic(
                    "doc-unknown-ci-job",
                    f"{repository.relative(path)} lists `{name}` as a CI job, which "
                    f"{CI_WORKFLOW} does not declare",
                )

    for document in _language_specs(repository) + _agent_guidance(repository):
        yield from _check_cited_commands(
            repository, document, code_spans(document.read_text(encoding="utf-8"))
        )

    if repository.jobs is None:
        return
    for job in repository.jobs:
        if not repository.declares(job.identifier):
            continue
        scope = repository.graph.recipe(job.identifier).scope
        for audience in dict.fromkeys((None, scope)):
            spans = cited.get(audience)
            if spans is None or job.identifier in spans:
                continue
            yield Diagnostic(
                "doc-uncovered-ci-job",
                f"{repository.relative(maps[audience])} does not name the CI job "
                f"`{job.identifier}`; a map that omits a lane understates what gates a merge",
            )


_RULES = (
    _check_names,
    _check_order,
    _check_roles,
    _check_scheduling,
    _check_gate_ownership,
    _check_runtime,
    _check_runner_config,
    _check_layout,
    _check_ci,
    _check_documentation,
)


def _audit(root: Path, graph: GateGraph) -> list[Diagnostic]:
    """Every way *graph* and the repository at *root* break the contract.

    *graph* is resolved by the caller, which also reports where it came from
    when the audit fails.
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
        findings = _audit(root, graph)
    except (GateGraphError, OSError, ValueError, yaml.YAMLError) as exc:
        print(f"gate check FAILED: {exc}", file=sys.stderr)
        return 1

    if findings:
        report_failures(
            "gate check",
            f"the command graph at {graph.source} breaks core/spec/language-testing.md",
            findings,
        )
        return 1

    public = sum(1 for recipe in graph.recipes if not recipe.private)
    print(f"gate check OK: {public} public command(s) conform")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
