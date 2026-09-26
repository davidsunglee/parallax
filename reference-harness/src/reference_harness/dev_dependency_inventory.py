"""Fail when a project declares a development dependency nothing demonstrably
uses::

    uv run python -m reference_harness.dev_dependency_inventory <project-dir> <repository-root>

An import scan cannot show that a command-line tool or a type-stub package is
still needed, so every development dependency is classified here from what its
installed distribution provides, matched against what the repository does with
it:

- ``imported`` — one of its top-level modules is imported by a Python source
  under the project;
- ``invoked`` — one of its executables, or ``python -m`` one of its modules, is
  run through ``uv run`` against the project by a ``justfile`` recipe or a
  ``.github/workflows`` step;
- ``type-stubs`` — it ships ``<module>-stubs`` for a module a project source
  imports.

A dependency with no classification is a failure, as is one that is not
installed. Development dependencies are read from both
``[project.optional-dependencies] dev`` and ``[dependency-groups] dev``; a group
entry naming the project's own extra, such as ``<project>[dev]``, stands for that
extra's requirements. Either list holding anything but requirement strings, such
as an ``include-group`` table, or a group entry selecting an extra the project
does not declare, cannot be read and fails the check.

The check must run inside the project's own environment: installed metadata is
read from the given import paths, which the command line takes from the running
interpreter.
"""

from __future__ import annotations

import ast
import inspect
import os
import re
import shlex
import sys
import tomllib
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass
from importlib import metadata
from pathlib import Path
from typing import Any, Literal

import yaml

from reference_harness import ci_workflow
from reference_harness.diagnostics import Diagnostic, report_failures
from reference_harness.gate_graph import GateGraphError, load_graph

__all__ = ["Classification", "Evidence", "EvidenceKind", "Inventory", "audit", "main"]

EvidenceKind = Literal["imported", "invoked", "type-stubs"]

_DEV_GROUP = "dev"
_JUST_LINE_PREFIXES = "@-"
_WORKFLOWS = Path(".github") / "workflows"
_WORKFLOW_SUFFIXES = (".yml", ".yaml")
_STUBS_SUFFIX = "-stubs"
_SCRIPT_ENTRY_POINT_GROUPS = frozenset({"console_scripts", "gui_scripts"})
_SCRIPT_DIRECTORIES = frozenset({"bin", "Scripts"})
_SHELL_SEPARATORS = frozenset({"&&", "||", ";", "|", "&", "(", ")"})
_UV_PROJECT_OPTIONS = frozenset({"--directory", "--project"})
_UV_MODULE_OPTIONS = frozenset({"-m", "--module"})
_UV_VALUE_OPTIONS = frozenset(
    {
        "--cache-dir",
        "--color",
        "--config-file",
        "--default-index",
        "--env-file",
        "--exclude-newer",
        "--extra",
        "--extra-index-url",
        "--group",
        "--index",
        "--index-url",
        "--link-mode",
        "--no-group",
        "--only-group",
        "--package",
        "--prerelease",
        "--python",
        "--resolution",
        "--with",
        "--with-editable",
        "--with-requirements",
        "-p",
    }
)
_PYTHON_EXECUTABLE_RE = re.compile(r"python(?:3(?:\.\d+)?)?")
_REQUIREMENT_NAME_RE = re.compile(r"\s*([A-Za-z0-9](?:[A-Za-z0-9._-]*[A-Za-z0-9])?)")
_EXTRAS_RE = re.compile(r"\s*\[([^\]]*)\]")
_ENVIRONMENT_ASSIGNMENT_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*=")


@dataclass(frozen=True)
class Evidence:
    """One reason a development dependency is needed, and where it was seen."""

    kind: EvidenceKind
    witness: str


@dataclass(frozen=True)
class Classification:
    """A declared development dependency, by normalized distribution name, with
    every reason found for it. No evidence means it is unclassified."""

    dependency: str
    evidence: tuple[Evidence, ...]


@dataclass(frozen=True)
class Inventory:
    """The classification of every declared development dependency, and the
    problems that fail the check."""

    classifications: tuple[Classification, ...]
    diagnostics: tuple[Diagnostic, ...]


@dataclass(frozen=True)
class _Installed:
    top_level: frozenset[str]
    executables: frozenset[str]


@dataclass(frozen=True)
class _Invocation:
    executable: str | None
    module: str | None
    witness: str


def _normalized(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def _requirement_name_match(requirement: str) -> re.Match[str]:
    matched = _REQUIREMENT_NAME_RE.match(requirement)
    if matched is None:
        raise ValueError(f"not a requirement: {requirement!r}")
    return matched


def _requirement_name(requirement: str) -> str:
    return _normalized(_requirement_name_match(requirement).group(1))


def _self_extras(requirement: str, project_name: str) -> tuple[str, ...] | None:
    """The normalized extras *requirement* selects when it names the project
    itself, or ``None`` when it names another distribution."""
    named = _requirement_name_match(requirement)
    if _normalized(named.group(1)) != project_name:
        return None
    selected = _EXTRAS_RE.match(requirement, named.end())
    if selected is None:
        raise ValueError(f"`{requirement}` names the project itself without selecting an extra")
    return tuple(_normalized(extra) for extra in selected.group(1).split(",") if extra.strip())


def _table(value: Any, location: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{location} must be a table")
    table: Mapping[str, Any] = value
    return table


def _requirement_strings(entries: Any, location: str) -> tuple[str, ...]:
    if not isinstance(entries, list) or not all(isinstance(entry, str) for entry in entries):
        raise ValueError(f"{location} must be a list of requirement strings")
    listed: list[str] = entries
    return tuple(listed)


def _development_requirements(manifest: Mapping[str, Any]) -> tuple[str, ...]:
    """Every requirement the development extra and development group declare,
    with a group entry naming one of the project's own extras replaced by that
    extra's requirements."""
    project = _table(manifest.get("project", {}), "[project]")
    name = _normalized(str(project.get("name", "")))
    optional = _table(project.get("optional-dependencies", {}), "[project.optional-dependencies]")
    groups = _table(manifest.get("dependency-groups", {}), "[dependency-groups]")
    extras = {_normalized(extra): entries for extra, entries in optional.items()}
    requirements = list(
        _requirement_strings(
            extras.get(_DEV_GROUP, []), f"[project.optional-dependencies] {_DEV_GROUP}"
        )
    )
    group_location = f"[dependency-groups] {_DEV_GROUP}"
    for entry in _requirement_strings(groups.get(_DEV_GROUP, []), group_location):
        selected = _self_extras(entry, name)
        if selected is None:
            requirements.append(entry)
            continue
        for extra in selected:
            if extra not in extras:
                raise ValueError(
                    f"`{entry}` in {group_location} selects the extra `{extra}`, which "
                    f"[project.optional-dependencies] does not declare"
                )
            requirements.extend(
                _requirement_strings(extras[extra], f"[project.optional-dependencies] {extra}")
            )
    return tuple(requirements)


def _python_sources(project: Path) -> Iterator[Path]:
    for directory, subdirectories, files in os.walk(project):
        subdirectories[:] = sorted(
            name for name in subdirectories if not name.startswith(".") and name != "__pycache__"
        )
        for name in sorted(files):
            if name.endswith(".py"):
                yield Path(directory, name)


def _top_level_imports(tree: ast.AST) -> Iterator[str]:
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                yield alias.name.partition(".")[0]
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            yield node.module.partition(".")[0]


def _imported_modules(project: Path) -> dict[str, str]:
    """Each top-level module a project source imports, with the first source
    importing it."""
    found: dict[str, str] = {}
    for source in _python_sources(project):
        tree = ast.parse(source.read_text(encoding="utf-8"), filename=str(source))
        for module in _top_level_imports(tree):
            found.setdefault(module, source.relative_to(project).as_posix())
    return found


def _simple_commands(script: str) -> Iterator[list[str]]:
    """Each simple command in a shell *script*, as words, with any leading
    environment assignments dropped."""
    for line in script.replace("\\\n", " ").splitlines():
        lexer = shlex.shlex(line, posix=True, punctuation_chars=True)
        lexer.whitespace_split = True
        try:
            words = list(lexer)
        except ValueError:
            words = line.split()
        command: list[str] = []
        for word in [*words, ";"]:
            if word not in _SHELL_SEPARATORS:
                if command or not _ENVIRONMENT_ASSIGNMENT_RE.match(word):
                    command.append(word)
            elif command:
                yield command
                command = []


def _python_module(arguments: Iterator[str]) -> str | None:
    for argument in arguments:
        if argument == "-m":
            return next(arguments, None)
        if argument.startswith("-m"):
            return argument[2:]
        if argument == "-c" or not argument.startswith("-"):
            return None
    return None


def _uv_run(words: Sequence[str], directory: Path) -> tuple[Path, str | None, str | None] | None:
    """The project directory, executable, and module a ``uv run`` command
    resolves to, or ``None`` when *words* is not one."""
    if list(words[:2]) != ["uv", "run"]:
        return None
    project = directory
    arguments = iter(words[2:])
    for word in arguments:
        option, _, attached = word.partition("=")
        if option in _UV_PROJECT_OPTIONS:
            project = directory / (attached or next(arguments, ""))
        elif option in _UV_MODULE_OPTIONS:
            return project, None, attached or next(arguments, None)
        elif option in _UV_VALUE_OPTIONS and not attached:
            next(arguments, None)
        elif not word.startswith("-"):
            name = Path(word).name
            if _PYTHON_EXECUTABLE_RE.fullmatch(name):
                return project, name, _python_module(arguments)
            return project, name, None
    return None


def _project_invocations(
    script: str, directory: Path, project: Path, witness: str
) -> Iterator[_Invocation]:
    """Each ``uv run`` in *script* that runs against *project*, following the
    ``cd`` commands that move the script out of *directory*."""
    current = directory
    for words in _simple_commands(script):
        if words[0] == "cd" and len(words) == 2:
            current = current / words[1]
            continue
        resolved = _uv_run(words, current)
        if resolved is None:
            continue
        target, executable, module = resolved
        if target.resolve().is_relative_to(project):
            yield _Invocation(
                executable, None if module is None else module.partition(".")[0], witness
            )


def _scripts(repository: Path) -> Iterator[tuple[str, Path, str]]:
    """Every shell script the repository's commands run: each script, the
    directory it starts in, and a witness naming it."""
    graph = load_graph(repository)
    for recipe in graph.recipes:
        for line in recipe.body:
            script = graph.expand(line).lstrip(_JUST_LINE_PREFIXES)
            yield script, graph.source.parent, f"just {recipe.name}"
    workflows = repository / _WORKFLOWS
    if not workflows.is_dir():
        return
    for workflow in sorted(workflows.iterdir()):
        if workflow.suffix not in _WORKFLOW_SUFFIXES:
            continue
        for job in ci_workflow.jobs(workflow) or ():
            for step in job.steps:
                start = repository / (step.working_directory or ".")
                witness = f"{workflow.relative_to(repository).as_posix()} job {job.identifier}"
                yield step.command, start, witness


def _invocations(project: Path, repository: Path) -> list[_Invocation]:
    return [
        invocation
        for script, directory, witness in _scripts(repository)
        for invocation in _project_invocations(script, directory, project, witness)
    ]


def _top_level_name(file: metadata.PackagePath) -> str | None:
    parts = file.parts
    name = parts[0] if len(parts) > 1 else inspect.getmodulename(file.name)
    return None if name is None or "." in name else name


def _script_name(file: metadata.PackagePath) -> str | None:
    parts = file.parts
    if len(parts) < 2 or parts[0] != ".." or parts[-2] not in _SCRIPT_DIRECTORIES:
        return None
    return parts[-1].removesuffix(".exe")


def _installed(name: str, site_paths: Sequence[str]) -> _Installed | None:
    distribution = next(iter(metadata.distributions(name=name, path=list(site_paths))), None)
    if distribution is None:
        return None
    files = distribution.files or ()
    declared = (distribution.read_text("top_level.txt") or "").split()
    top_level = set(declared) or {
        found for file in files if (found := _top_level_name(file)) is not None
    }
    executables = {
        entry_point.name
        for entry_point in distribution.entry_points
        if entry_point.group in _SCRIPT_ENTRY_POINT_GROUPS
    }
    executables.update(found for file in files if (found := _script_name(file)) is not None)
    return _Installed(frozenset(top_level), frozenset(executables))


def _evidence(
    installed: _Installed, imports: Mapping[str, str], invocations: Sequence[_Invocation]
) -> tuple[Evidence, ...]:
    found: list[Evidence] = [
        Evidence("imported", f"`{module}` by {imports[module]}")
        for module in sorted(installed.top_level & imports.keys())
    ]
    for invocation in invocations:
        if invocation.executable in installed.executables:
            found.append(Evidence("invoked", f"`{invocation.executable}` by {invocation.witness}"))
        elif invocation.module in installed.top_level:
            found.append(Evidence("invoked", f"`-m {invocation.module}` by {invocation.witness}"))
    for name in sorted(installed.top_level):
        stubbed = name.removesuffix(_STUBS_SUFFIX)
        if name.endswith(_STUBS_SUFFIX) and stubbed in imports:
            found.append(Evidence("type-stubs", f"`{name}` for `{stubbed}` in {imports[stubbed]}"))
    return tuple(dict.fromkeys(found))


def audit(project: Path, repository: Path, site_paths: Sequence[str]) -> Inventory:
    """Classify every development dependency *project* declares.

    Commands are read from the ``justfile`` and ``.github/workflows`` at
    *repository*; installed distributions from *site_paths*. Raises
    ``GateGraphError``, ``OSError``, ``SyntaxError``, ``ValueError``, or
    ``yaml.YAMLError`` when an input cannot be read.
    """
    project = project.resolve()
    repository = repository.resolve()
    with (project / "pyproject.toml").open("rb") as manifest:
        requirements = _development_requirements(tomllib.load(manifest))
    diagnostics: list[Diagnostic] = []
    declared = sorted({_requirement_name(requirement) for requirement in requirements})
    imports = _imported_modules(project)
    invocations = _invocations(project, repository)
    classifications: list[Classification] = []
    for name in declared:
        installed = _installed(name, site_paths)
        if installed is None:
            diagnostics.append(
                Diagnostic(
                    "dev-dependency-not-installed",
                    f"`{name}` is not installed, so what it provides cannot be classified",
                )
            )
            continue
        evidence = _evidence(installed, imports, invocations)
        if not evidence:
            diagnostics.append(
                Diagnostic(
                    "dev-dependency-unclassified",
                    f"`{name}` is neither imported, invoked through `uv run`, nor a provider "
                    f"of type stubs for an imported module",
                )
            )
        classifications.append(Classification(name, evidence))
    return Inventory(tuple(classifications), tuple(diagnostics))


def _usage() -> str:
    return (
        "usage: python -m reference_harness.dev_dependency_inventory "
        "<project-dir> <repository-root>"
    )


def _print_table(inventory: Inventory) -> None:
    for classification in inventory.classifications:
        print(f"  {classification.dependency}")
        for evidence in classification.evidence:
            print(f"    {evidence.kind}: {evidence.witness}")


def main(argv: list[str]) -> int:
    """Audit the project at the first argument against the repository at the
    second.

    Exit codes: 0 — every development dependency is classified; 1 — one is not,
    or an input could not be read; 2 — usage error.
    """
    if len(argv) != 2:
        print(_usage(), file=sys.stderr)
        return 2
    project, repository = (Path(argument).resolve() for argument in argv)
    try:
        inventory = audit(project, repository, sys.path)
    except (GateGraphError, OSError, SyntaxError, ValueError, yaml.YAMLError) as exc:
        print(f"development-dependency inventory FAILED: {exc}", file=sys.stderr)
        return 1
    if inventory.diagnostics:
        report_failures(
            "development-dependency inventory",
            f"the development dependencies {project / 'pyproject.toml'} declares",
            inventory.diagnostics,
        )
        return 1
    print(
        f"development-dependency inventory OK: "
        f"{len(inventory.classifications)} development dependency(ies) classified"
    )
    _print_table(inventory)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
