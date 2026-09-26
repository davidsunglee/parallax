"""Fail when a Python development dependency has no checked reason to exist.

Every requirement in the workspace root's ``[dependency-groups]`` must earn at
least one classification, each derived from the repository and the installed
environment rather than asserted:

* **imported** — a module under ``tests/`` or ``tools/`` imports one of the
  import packages the installed distribution provides. A workspace member
  provides its ``parallax.<scope>`` package. A distribution that ships no module
  of its own provides what its unconditional requirements provide, which is how
  a metapackage release of a library is recognized.
* **invoked** — a ``uv run`` command the root ``justfile`` or a GitHub workflow
  runs in the Python workspace names a console script or installed script the
  distribution provides, or runs ``python -m`` on a module it provides. A
  justfile line is in the workspace when it changes into ``languages/python``
  (literally or through a variable holding that path); a workflow command is
  when its step or job runs there, or it passes ``--project``/``--directory``
  naming it.
* **type stubs** — every package the distribution installs is a PEP 561
  ``<module>-stubs`` package, and ``packages/*/src``, ``tests/`` or ``tools/``
  imports one of those modules.
* **pytest plugin** — the distribution registers a ``pytest11`` entry point
  and one of the options :data:`PYTEST_PLUGINS` records for it appears in a
  workspace ``pytest`` command or in ``[tool.pytest.ini_options].addopts``. A
  plugin is used through options, not imports or scripts, so this is the one
  classification that needs an explicit record, and a record for a
  distribution the groups no longer list is itself a finding.

A requirement the environment does not have installed cannot be classified and
fails, as does any unclassified one.

Usage: ``uv run python tools/check_dev_dependencies.py`` (from
``languages/python``); prints each dependency's classifications and exits
non-zero on any finding.
"""

from __future__ import annotations

import importlib.metadata
import re
import shlex
import sys
from collections.abc import Iterable, Iterator, Mapping
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Final, Protocol, cast

import yaml

from python_workspace import (
    Workspace,
    imported_modules,
    load_workspace,
    module_name,
    normalize,
    python_files,
    read_toml,
    requirement_name,
    strings,
    table,
)

PY_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = PY_ROOT.parents[1]
WORKSPACE_PATH = PurePosixPath("languages/python")

_STUBS_SUFFIX = "-stubs"


@dataclass(frozen=True, slots=True)
class PytestPlugin:
    options: re.Pattern[str]
    rationale: str


PYTEST_PLUGINS: Final[Mapping[str, PytestPlugin]] = {
    "pytest-cov": PytestPlugin(
        re.compile(r"--(no-)?cov(-[a-z-]+)?(=.*)?"),
        "branch coverage and its fail-under threshold are measured through --cov",
    ),
    "pytest-xdist": PytestPlugin(
        re.compile(r"-n|--numprocesses(=.*)?|--dist(=.*)?"),
        "the database-free, database, and cost classes run on parallel workers through -n",
    ),
}


class DistributionMetadata(Protocol):
    """What the check reads about an installed distribution."""

    def import_names(self, distribution: str) -> frozenset[str]:
        """Top-level import packages the distribution installs."""
        ...

    def commands(self, distribution: str) -> frozenset[str]:
        """Console scripts and installed scripts the distribution provides."""
        ...

    def pytest_plugin(self, distribution: str) -> bool: ...


class InstalledMetadata:
    """:class:`DistributionMetadata` read from the running environment.

    Raises :class:`importlib.metadata.PackageNotFoundError` for a distribution
    that is not installed."""

    def __init__(self) -> None:
        self._provided: dict[str, set[str]] = {}
        for module, distributions in importlib.metadata.packages_distributions().items():
            for distribution in distributions:
                self._provided.setdefault(normalize(distribution), set()).add(module)

    def import_names(self, distribution: str) -> frozenset[str]:
        own = self._provided.get(normalize(distribution))
        if own:
            return frozenset(own)
        requirements = importlib.metadata.requires(distribution) or []
        return frozenset(
            name
            for requirement in requirements
            if "extra" not in requirement.partition(";")[2]
            for name in self._provided.get(requirement_name(requirement), ())
        )

    def commands(self, distribution: str) -> frozenset[str]:
        found = importlib.metadata.distribution(distribution)
        scripts = {entry.name for entry in found.entry_points if entry.group == "console_scripts"}
        scripts.update(
            PurePosixPath(str(path)).name.removesuffix(".exe")
            for path in found.files or ()
            if PurePosixPath(str(path)).parent.name in {"bin", "Scripts"}
            and str(path).startswith("..")
        )
        return frozenset(scripts)

    def pytest_plugin(self, distribution: str) -> bool:
        found = importlib.metadata.distribution(distribution)
        return any(entry.group == "pytest11" for entry in found.entry_points)


@dataclass(frozen=True, slots=True)
class Command:
    """One ``uv run`` command, from the executable on, and where it is written."""

    argv: tuple[str, ...]
    origin: str


@dataclass(frozen=True, slots=True)
class Evidence:
    """What the repository offers to classify against."""

    tooling_imports: Mapping[str, str]
    source_imports: Mapping[str, str]
    commands: tuple[Command, ...]
    pytest_addopts: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class Classification:
    requirement: str
    reasons: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class Report:
    classifications: tuple[Classification, ...]
    findings: tuple[str, ...]


def check(
    workspace: Workspace,
    repo_root: Path,
    metadata: DistributionMetadata,
    plugins: Mapping[str, PytestPlugin] = PYTEST_PLUGINS,
) -> Report:
    """Classify every requirement in ``workspace``'s dependency groups."""
    evidence = _gather(workspace, repo_root)
    listed = _development_requirements(workspace.root)
    classifications: list[Classification] = []
    findings: list[str] = []
    for group, requirement in listed:
        try:
            reasons = _classify(requirement, workspace, evidence, metadata, plugins)
        except importlib.metadata.PackageNotFoundError:
            findings.append(f"{group}: {requirement} is not installed, so it cannot be classified")
            continue
        classifications.append(Classification(requirement, reasons))
        if not reasons:
            findings.append(f"{group}: {requirement} is unclassified")
    names = {requirement_name(requirement) for _, requirement in listed}
    findings += [
        f"PYTEST_PLUGINS records {plugin}, which no dependency group lists"
        for plugin in sorted(plugins.keys() - names)
    ]
    return Report(tuple(classifications), tuple(findings))


def _development_requirements(root: Path) -> list[tuple[str, str]]:
    groups = table(read_toml(root / "pyproject.toml"), "dependency-groups")
    return [(group, requirement) for group in groups for requirement in strings(groups[group])]


def _classify(
    requirement: str,
    workspace: Workspace,
    evidence: Evidence,
    metadata: DistributionMetadata,
    plugins: Mapping[str, PytestPlugin],
) -> tuple[str, ...]:
    name = requirement_name(requirement)
    member = next((member for member in workspace.members if member.name == name), None)
    packages = frozenset({member.package}) if member is not None else metadata.import_names(name)
    reasons = [
        *_imported(packages, evidence.tooling_imports),
        *_type_stubs(packages, evidence),
    ]
    if member is None:
        reasons += _invoked(metadata.commands(name), packages, evidence.commands)
        reasons += _plugin(plugins.get(name), name, evidence, metadata)
    return tuple(reasons)


def _provides(packages: Iterable[str], module: str) -> bool:
    return any(module == package or module.startswith(f"{package}.") for package in packages)


def _imported(packages: frozenset[str], imports: Mapping[str, str]) -> list[str]:
    site = next((site for module, site in imports.items() if _provides(packages, module)), None)
    return [] if site is None else [f"imported by tests or tooling ({site})"]


def _type_stubs(packages: frozenset[str], evidence: Evidence) -> list[str]:
    if not packages or not all(package.endswith(_STUBS_SUFFIX) for package in packages):
        return []
    stubbed = {package.removesuffix(_STUBS_SUFFIX) for package in packages}
    everywhere = {**evidence.tooling_imports, **evidence.source_imports}
    site = next((site for module, site in everywhere.items() if _provides(stubbed, module)), None)
    return [] if site is None else [f"type stubs for {', '.join(sorted(stubbed))} ({site})"]


def _invoked(
    scripts: frozenset[str], packages: frozenset[str], commands: Iterable[Command]
) -> list[str]:
    for command in commands:
        executable = command.argv[0]
        if executable in scripts or (
            executable == "python"
            and len(command.argv) > 2
            and command.argv[1] == "-m"
            and _provides(packages, command.argv[2])
        ):
            shown = " ".join(command.argv[: 3 if executable == "python" else 1])
            return [f"invoked by `uv run {shown}` ({command.origin})"]
    return []


def _plugin(
    plugin: PytestPlugin | None, name: str, evidence: Evidence, metadata: DistributionMetadata
) -> list[str]:
    if plugin is None or not metadata.pytest_plugin(name):
        return []
    for origin, options in _pytest_options(evidence):
        used = next((option for option in options if plugin.options.fullmatch(option)), None)
        if used is not None:
            return [f"pytest plugin: {plugin.rationale} ({used} in {origin})"]
    return []


def _pytest_options(evidence: Evidence) -> Iterator[tuple[str, tuple[str, ...]]]:
    yield "[tool.pytest.ini_options].addopts", evidence.pytest_addopts
    for command in evidence.commands:
        argv = command.argv
        if argv[0] == "pytest":
            yield command.origin, argv[1:]
        elif argv[:3] == ("python", "-m", "pytest"):
            yield command.origin, argv[3:]


def _gather(workspace: Workspace, repo_root: Path) -> Evidence:
    root = workspace.root
    tooling: dict[str, str] = {}
    for directory in (root / "tests", root / "tools"):
        tooling.update(_imports_under(root, directory, source_root=None))
    source: dict[str, str] = {}
    for member in workspace.members:
        source.update(_imports_under(root, member.source, source_root=member.source.parents[1]))
    addopts = table(read_toml(root / "pyproject.toml"), "tool", "pytest", "ini_options").get(
        "addopts", ""
    )
    return Evidence(
        tooling_imports=tooling,
        source_imports=source,
        commands=(*_justfile_commands(repo_root / "justfile"), *_workflow_commands(repo_root)),
        pytest_addopts=tuple(shlex.split(addopts)) if isinstance(addopts, str) else (),
    )


def _imports_under(root: Path, directory: Path, source_root: Path | None) -> dict[str, str]:
    found: dict[str, str] = {}
    if not directory.is_dir():
        return found
    for path in python_files(directory):
        module = None if source_root is None else module_name(path, source_root)
        site = path.relative_to(root).as_posix()
        for imported, line in imported_modules(path, module).items():
            found.setdefault(imported, f"{site}:{line}")
    return found


_UV_RUN_VALUE_OPTIONS: Final = frozenset(
    {
        "--with",
        "--with-editable",
        "--with-requirements",
        "--project",
        "--directory",
        "--python",
        "-p",
        "--group",
        "--only-group",
        "--no-group",
        "--extra",
        "--package",
        "--env-file",
        "--index",
    }
)


def uv_run_commands(text: str, in_workspace: bool, origin: str) -> list[Command]:
    """Each ``uv run`` command in one line of shell, if it runs in the workspace."""
    commands: list[Command] = []
    for segment in re.split(r"&&|\|\||[;|]", text):
        words = _words(segment)
        if words[:2] != ["uv", "run"]:
            continue
        argv, directory = _uv_run_argv(words[2:])
        if argv and (in_workspace or directory == WORKSPACE_PATH):
            commands.append(Command(tuple(argv), origin))
    return commands


def _words(segment: str) -> list[str]:
    try:
        return shlex.split(segment)
    except ValueError:
        return segment.split()


def _uv_run_argv(words: list[str]) -> tuple[list[str], PurePosixPath | None]:
    directory: PurePosixPath | None = None
    index = 0
    while index < len(words) and words[index].startswith("-"):
        option, _, value = words[index].partition("=")
        if option in _UV_RUN_VALUE_OPTIONS and not value and index + 1 < len(words):
            index += 1
            value = words[index]
        if option in {"--project", "--directory"}:
            directory = PurePosixPath(value)
        index += 1
    return words[index:], directory


def _justfile_commands(justfile: Path) -> list[Command]:
    if not justfile.is_file():
        return []
    lines = justfile.read_text(encoding="utf-8").splitlines()
    variables = [
        match.group(1)
        for line in lines
        if (match := re.fullmatch(rf'(\w+)\s*:=\s*"{WORKSPACE_PATH}/?"\s*', line))
    ]
    places = [re.escape(str(WORKSPACE_PATH))] + [rf"\{{\{{\s*{name}\s*\}}\}}" for name in variables]
    enters = re.compile(rf"\bcd\s+(?:{'|'.join(places)})/?\s*(?:&&|;|$)")
    commands: list[Command] = []
    for number, line in enumerate(lines, start=1):
        if line.lstrip().startswith("#"):
            continue
        commands += uv_run_commands(line, bool(enters.search(line)), f"justfile:{number}")
    return commands


def _workflow_commands(repo_root: Path) -> list[Command]:
    directory = repo_root / ".github" / "workflows"
    if not directory.is_dir():
        return []
    commands: list[Command] = []
    for path in sorted([*directory.glob("*.yml"), *directory.glob("*.yaml")]):
        document = yaml.safe_load(path.read_text(encoding="utf-8"))
        origin = path.relative_to(repo_root).as_posix()
        jobs = table(cast("Mapping[str, Any]", document or {}), "jobs")
        for job_name in jobs:
            commands += _job_commands(table(jobs, job_name), f"{origin} {job_name}")
    return commands


def _job_commands(job: Mapping[str, Any], origin: str) -> list[Command]:
    default = table(job, "defaults", "run").get("working-directory")
    commands: list[Command] = []
    steps = job.get("steps", [])
    for step in cast("list[Any]", steps) if isinstance(steps, list) else []:
        if not isinstance(step, dict):
            continue
        step_map = cast("Mapping[str, Any]", step)
        run = step_map.get("run")
        if not isinstance(run, str):
            continue
        place = step_map.get("working-directory", default)
        in_workspace = isinstance(place, str) and PurePosixPath(place) == WORKSPACE_PATH
        for line in run.splitlines():
            commands += uv_run_commands(line, in_workspace, origin)
    return commands


def main(argv: list[str] | None = None) -> int:
    del argv
    report = check(load_workspace(PY_ROOT), REPO_ROOT, InstalledMetadata())
    for classification in report.classifications:
        reasons = "; ".join(classification.reasons) or "UNCLASSIFIED"
        print(f"{classification.requirement}: {reasons}")
    if not report.findings:
        return 0
    for finding in report.findings:
        print(finding, file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
